import { normalizeElementPathsForTreeSync, normalizeTreePath } from '../xmlPaths'
import {
  applyLoadedChildren,
  findChoiceAlternative,
  findNodeByPath,
  findNodesForElementPath,
  findParentNode,
  injectXmlChildrenIntoAnyNode,
  walkTree,
} from './model'
import {
  addCheckedAncestors,
  enforceChoiceExclusivity,
  expandAncestorsOfChecked,
  pruneOrphanPaths,
} from './selection'

/** Rebuild children for every ANY container from the current XML element paths. */
export function refreshAnyContainersFromXml(treeRoot, elementPaths, modelOptions) {
  if (!treeRoot) return
  walkTree(treeRoot, (node) => {
    if (node._isAnyContainer) {
      injectXmlChildrenIntoAnyNode(node, elementPaths, modelOptions)
    }
  })
}

function matchedElPathsUnderAlternative(altNode, elPathSet) {
  const matched = new Set()
  walkTree(altNode, (n) => {
    if (n.isGroupLabel) return
    const el = normalizeTreePath(n.path)
    if (elPathSet.has(el)) matched.add(el)
  })
  if (!altNode.isGroupLabel) {
    const normBase = normalizeTreePath(altNode.path)
    for (const elPath of elPathSet) {
      if (elPath === normBase || elPath.startsWith(`${normBase}.`)) matched.add(elPath)
    }
  }
  return matched
}

function scoreAlternativeForXml(altNode, siblingAlts, elPathSet) {
  const matched = matchedElPathsUnderAlternative(altNode, elPathSet)
  if (!matched.size) return 0

  const siblingMatched = new Set()
  for (const sib of siblingAlts) {
    if (sib === altNode) continue
    matchedElPathsUnderAlternative(sib, elPathSet).forEach((p) => siblingMatched.add(p))
  }

  let score = 0
  for (const p of matched) {
    score += siblingMatched.has(p) ? 1 : 100
  }
  return score
}

function isAlternativePreferredByPaths(alt, preferPaths) {
  if (!preferPaths?.size) return false
  return [...preferPaths].some((p) => p === alt.path || p.startsWith(`${alt.path}.`))
}

export function resolveChoiceSelectionsFromXml(
  root,
  elPathSet,
  selections = new Map(),
  preferPaths = null,
) {
  if (!root) return selections
  // Iterative DFS to avoid call-stack overflow on large loaded trees.
  const stack = [root]
  while (stack.length > 0) {
    const node = stack.pop()
    if (node._isChoiceGroup) {
      const alts = node.children || []
      let bestAlt = null
      let bestScore = 0
      let bestPreferred = false
      for (const alt of alts) {
        const score = scoreAlternativeForXml(alt, alts, elPathSet)
        const preferred = isAlternativePreferredByPaths(alt, preferPaths)
        if (
          score > bestScore
          || (score === bestScore && score > 0 && preferred && !bestPreferred)
        ) {
          bestScore = score
          bestAlt = alt
          bestPreferred = preferred
        }
      }
      if (bestAlt && bestScore > 0) {
        selections.set(node.path, bestAlt.path)
        stack.push(bestAlt)
      }
    } else {
      const children = node.children
      if (children) {
        for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
      }
    }
  }
  return selections
}

export function isNodeUnderChoiceSelections(node, selections, treeRoot) {
  let current = node
  while (current) {
    const parent = findParentNode(current.path, treeRoot)
    if (!parent) break
    if (parent._isChoiceGroup) {
      const selectedAltPath = selections.get(parent.path)
      if (selectedAltPath) {
        const alt = findChoiceAlternative(parent, current)
        if (!alt || alt.path !== selectedAltPath) return false
      }
    }
    current = parent
  }
  return true
}

export function pickNodeForElementPath(candidates, selections, treeRoot) {
  if (!candidates.length) return null
  if (candidates.length === 1) return candidates[0]
  const filtered = candidates.filter((n) => isNodeUnderChoiceSelections(n, selections, treeRoot))
  return filtered[0] || null
}

export async function loadNodeIfNeeded(node, getElementTree, isStale, modelOptions) {
  if (!node?._refName || node._loaded || isStale()) return
  const data = await getElementTree(node._refName)
  if (isStale()) return
  applyLoadedChildren(node, data.content_model, modelOptions)
}

export async function ensureElementPathLoaded(
  elPath,
  treeRoot,
  getElementTree,
  isStale,
  selections,
  modelOptions,
) {
  // Pre-build the set of path prefixes that can lead to elPath so that
  // recursive DTD schemas (A contains B contains A …) cannot produce an
  // unbounded tree — only the branch toward elPath is ever expanded.
  const neededPrefixes = new Set()
  const parts = elPath.split('.')
  let prefix = ''
  for (const part of parts) {
    prefix = prefix ? `${prefix}.${part}` : part
    neededPrefixes.add(prefix)
  }

  // Iterative DFS — avoids unbounded async call-stack frames that caused OOM.
  const stack = [treeRoot]
  while (stack.length > 0) {
    if (isStale()) return null
    const node = stack.pop()
    if (!node) continue

    if (!node.isGroupLabel && normalizeTreePath(node.path) === elPath) return node

    await loadNodeIfNeeded(node, getElementTree, isStale, modelOptions)
    if (isStale()) return null

    const children = node.children || []
    // Push in reverse order so left-to-right DFS order is preserved.
    for (let i = children.length - 1; i >= 0; i--) {
      const child = children[i]
      if (node._isChoiceGroup) {
        const selectedAltPath = selections.get(node.path)
        if (selectedAltPath && child.path !== selectedAltPath) continue
      }
      // Only explore branches that can lead to elPath — prevents unbounded
      // expansion in recursive schemas (e.g. A → B → A → …).
      if (!neededPrefixes.has(normalizeTreePath(child.path))) continue
      stack.push(child)
    }
  }

  const candidates = findNodesForElementPath(elPath, treeRoot)
  return pickNodeForElementPath(candidates, selections, treeRoot)
}

export async function ensureTreeLoadedForElementPaths(
  elementPaths,
  treeRoot,
  getElementTree,
  isStale,
  modelOptions,
  selections = new Map(),
) {
  if (!treeRoot || isStale()) return
  const pathSet = new Set(elementPaths)

  // Pre-build a set of all path prefixes that are needed so subtreeNeeded()
  // is O(depth) instead of O(pathSet.size) per node.
  const neededPrefixes = new Set()
  for (const p of pathSet) {
    const parts = p.split('.')
    let prefix = ''
    for (const part of parts) {
      prefix = prefix ? `${prefix}.${part}` : part
      neededPrefixes.add(prefix)
    }
  }

  function subtreeNeeded(node) {
    return neededPrefixes.has(normalizeTreePath(node.path))
  }

  // Iterative BFS — avoids unbounded async call-stack frames that caused OOM.
  const queue = [treeRoot]
  while (queue.length > 0) {
    if (isStale()) return
    const node = queue.shift()

    if (subtreeNeeded(node)) {
      if (node._refName && !node._loaded) {
        const data = await getElementTree(node._refName)
        if (isStale()) return
        applyLoadedChildren(node, data.content_model, modelOptions)
        node.expanded = true
      } else if (node._isAnyContainer && !node._loaded) {
        injectXmlChildrenIntoAnyNode(node, elementPaths, modelOptions)
        node.expanded = true
      }
    }

    for (const child of node.children || []) {
      if (node._isChoiceGroup) {
        const selectedAltPath = selections.get(node.path)
        if (selectedAltPath && child.path !== selectedAltPath) continue
      }
      // Only explore branches that can lead to a needed path.
      // This keeps queue size bounded by depth × needed-paths instead of full tree size.
      if (neededPrefixes.has(normalizeTreePath(child.path))) {
        queue.push(child)
      }
    }
  }
}

// Structural paths beyond this cap are not synced to the DTD tree.
// Paths are sorted shallowest-first by normalizeElementPathsForTreeSync so the
// most important structure is always captured first.
const MAX_SYNC_PATHS = 500

export async function buildCheckedPathsFromElementPaths({
  elementPaths,
  treeRoot,
  getElementTree,
  isStale,
  preferPaths,
  modelOptions,
}) {
  const allSyncPaths = normalizeElementPathsForTreeSync(elementPaths)
  const syncPaths = allSyncPaths.length > MAX_SYNC_PATHS
    ? allSyncPaths.slice(0, MAX_SYNC_PATHS)
    : allSyncPaths
  const elPathSet = new Set(syncPaths)
  const modelOptionsWithXml = { ...modelOptions, xmlElementPaths: syncPaths }

  refreshAnyContainersFromXml(treeRoot, syncPaths, modelOptionsWithXml)

  let choiceSelections = resolveChoiceSelectionsFromXml(
    treeRoot,
    elPathSet,
    new Map(),
    preferPaths,
  )

  await ensureTreeLoadedForElementPaths(
    syncPaths,
    treeRoot,
    getElementTree,
    isStale,
    modelOptionsWithXml,
    choiceSelections,
  )
  if (isStale()) return null

  refreshAnyContainersFromXml(treeRoot, syncPaths, modelOptionsWithXml)

  choiceSelections = resolveChoiceSelectionsFromXml(
    treeRoot,
    elPathSet,
    new Map(),
    preferPaths,
  )

  for (const elPath of syncPaths) {
    await ensureElementPathLoaded(
      elPath,
      treeRoot,
      getElementTree,
      isStale,
      choiceSelections,
      modelOptionsWithXml,
    )
  }
  if (isStale()) return null

  choiceSelections = resolveChoiceSelectionsFromXml(
    treeRoot,
    elPathSet,
    new Map(),
    preferPaths,
  )

  const nextChecked = new Set()
  for (const elPath of syncPaths) {
    const candidates = findNodesForElementPath(elPath, treeRoot)
    const node = pickNodeForElementPath(candidates, choiceSelections, treeRoot)
    if (!node || !isNodeUnderChoiceSelections(node, choiceSelections, treeRoot)) continue
    nextChecked.add(node.path)
    addCheckedAncestors(nextChecked, node, treeRoot)
  }

  for (const altPath of choiceSelections.values()) {
    nextChecked.add(altPath)
    const altNode = findNodeByPath(altPath, treeRoot)
    if (altNode) addCheckedAncestors(nextChecked, altNode, treeRoot)
  }

  return nextChecked
}

export function finalizeCheckedPathsFromXml(checkedPaths, treeRoot) {
  enforceChoiceExclusivity(treeRoot, checkedPaths)
  pruneOrphanPaths(treeRoot, checkedPaths)
  expandAncestorsOfChecked(checkedPaths, treeRoot)
}

export function inferRootFromPaths(paths) {
  if (!paths?.length) return ''
  const tops = paths.filter((p) => !p.includes('.'))
  if (tops.length) return tops[0]
  const shortest = paths.reduce((a, b) => (a.length <= b.length ? a : b))
  return shortest.split('.')[0]
}
