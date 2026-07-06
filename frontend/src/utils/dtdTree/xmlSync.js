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
  node,
  elPathSet,
  selections = new Map(),
  preferPaths = null,
) {
  if (!node) return selections
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
      resolveChoiceSelectionsFromXml(bestAlt, elPathSet, selections, preferPaths)
    }
    return selections
  }
  for (const child of node.children || []) {
    resolveChoiceSelectionsFromXml(child, elPathSet, selections, preferPaths)
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
  async function walk(node) {
    if (isStale() || !node) return null
    if (!node.isGroupLabel && normalizeTreePath(node.path) === elPath) return node

    await loadNodeIfNeeded(node, getElementTree, isStale, modelOptions)

    for (const child of node.children || []) {
      if (node._isChoiceGroup) {
        const selectedAltPath = selections.get(node.path)
        if (selectedAltPath && child.path !== selectedAltPath) continue
      }
      const found = await walk(child)
      if (found) return found
    }
    return null
  }

  const found = await walk(treeRoot)
  if (found) return found

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

  function subtreeNeeded(node) {
    const elPath = normalizeTreePath(node.path)
    return [...pathSet].some((p) => p === elPath || p.startsWith(`${elPath}.`))
  }

  async function walkLoad(node) {
    if (isStale()) return
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
      await walkLoad(child)
    }
  }

  await walkLoad(treeRoot)
}

export async function buildCheckedPathsFromElementPaths({
  elementPaths,
  treeRoot,
  getElementTree,
  isStale,
  preferPaths,
  modelOptions,
}) {
  const syncPaths = normalizeElementPathsForTreeSync(elementPaths)
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
