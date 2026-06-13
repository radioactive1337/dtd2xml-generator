/**
 * Resolve child tree paths the same way as DtdTreeView.resolveChildPaths.
 * @returns {{ childPath: string, elementPath: string }}
 */
export function resolveChildTreePaths(parentPath, elementPath, parentKind, child, idx) {
  const childName = child.kind === 'REF' ? child.ref : `group-${idx}`
  if (parentKind === 'CHOICE' && child.kind === 'REF') {
    const childPath = `${elementPath}.${child.ref}`
    return { childPath, elementPath: childPath }
  }
  const childPath = `${parentPath}.${childName}`
  const nextElementPath = child.kind === 'REF' ? childPath : elementPath
  return { childPath, elementPath: nextElementPath }
}

function pathTailName(treePath) {
  const parts = treePath.split('.')
  return parts[parts.length - 1] || ''
}

/**
 * Expand a content model into descendant search states (no API calls).
 * @returns {Array<{ refToLoad: string, treePath: string, elementPath: string }>}
 */
export function expandModelBranches(model, treePath, elementPath) {
  const branches = []
  if (!model) return branches

  if (model.kind === 'REF') {
    const childPath = `${treePath}.${model.ref}`
    branches.push({
      refToLoad: model.ref,
      treePath: childPath,
      elementPath: childPath,
    })
    return branches
  }

  if (model.kind === 'SEQUENCE' || model.kind === 'CHOICE') {
    const kind = model.kind
    for (let idx = 0; idx < (model.children || []).length; idx++) {
      const child = model.children[idx]
      const { childPath, elementPath: childElPath } = resolveChildTreePaths(
        treePath,
        elementPath,
        kind,
        child,
        idx,
      )

      if (child.kind === 'REF') {
        branches.push({
          refToLoad: child.ref,
          treePath: childPath,
          elementPath: childElPath,
        })
      } else if (child.kind === 'SEQUENCE' || child.kind === 'CHOICE') {
        branches.push(...expandModelBranches(child, childPath, childElPath))
      }
    }
  }

  return branches
}

/**
 * BFS from rootElement through content models to find a tree path for targetName.
 * @param {string} rootElement
 * @param {string} targetName
 * @param {(elementName: string) => Promise<{ content_model?: object }>} getElementTree
 * @returns {Promise<string | null>} dot path like PayDoc.Body.Record.Field
 */
export async function findPathsToElement(rootElement, targetName, getElementTree) {
  const root = rootElement?.trim()
  const target = targetName?.trim()
  if (!root || !target) return null

  if (root === target) return root

  const cache = new Map()
  async function loadModel(elementName) {
    if (!cache.has(elementName)) {
      const data = await getElementTree(elementName)
      cache.set(elementName, data?.content_model ?? null)
    }
    return cache.get(elementName)
  }

  const queue = [{ refToLoad: root, treePath: root, elementPath: root }]
  const expandedPaths = new Set()

  while (queue.length > 0) {
    const state = queue.shift()
    if (expandedPaths.has(state.treePath)) continue
    expandedPaths.add(state.treePath)

    const model = await loadModel(state.refToLoad)
    if (!model) continue

    const branches = expandModelBranches(model, state.treePath, state.elementPath)
    for (const branch of branches) {
      if (pathTailName(branch.treePath) === target) {
        return branch.treePath
      }
      queue.push(branch)
    }
  }

  return null
}
