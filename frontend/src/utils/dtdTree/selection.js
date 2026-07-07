import {
  collectDescendantPaths,
  findChoiceAlternative,
  findChoiceGroupAncestor,
  findNodeByPath,
  findParentNode,
  skipGroupLabelParent,
  walkTree,
} from './model'

export function removePathAndDescendants(path, checkedPaths, treeRoot) {
  checkedPaths.delete(path)
  for (const p of [...checkedPaths]) {
    if (p !== path && p.startsWith(`${path}.`)) {
      checkedPaths.delete(p)
    }
  }
  const node = findNodeByPath(path, treeRoot)
  if (node) {
    for (const childPath of collectDescendantPaths(node)) {
      checkedPaths.delete(childPath)
    }
  }
}

export function isChoiceAlternativeSelected(choiceGroup, alt, checkedPaths) {
  const prefix = `${alt.path}.`
  for (const p of checkedPaths) {
    if (p === alt.path || p.startsWith(prefix)) return true
  }
  return false
}

/** Required nodes apply only when every ancestor branch is selected (incl. CHOICE alt). */
export function isInActiveBranch(node, treeRoot, checkedPaths) {
  if (!node) return false
  let current = node
  while (true) {
    const parent = skipGroupLabelParent(current, treeRoot)
    if (!parent) return true

    if (parent._isChoiceGroup) {
      const alt = findChoiceAlternative(parent, current)
      if (!alt || !isChoiceAlternativeSelected(parent, alt, checkedPaths)) return false
    }

    if (!parent.required && !checkedPaths.has(parent.path)) {
      if (!hasCheckedDescendant(parent, checkedPaths)) return false
    }

    current = parent
  }
}

export function enforceChoiceExclusivity(treeRoot, checkedPaths) {
  if (!treeRoot) return
  const stack = [treeRoot]
  while (stack.length > 0) {
    const node = stack.pop()
    if (node._isChoiceGroup) {
      const selected = (node.children || []).filter((c) =>
        isChoiceAlternativeSelected(node, c, checkedPaths),
      )
      for (let i = 1; i < selected.length; i++) {
        removePathAndDescendants(selected[i].path, checkedPaths, treeRoot)
      }
    }
    const children = node.children
    if (children) {
      for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
    }
  }
}

/** Drop checked paths that belong to non-selected CHOICE alternatives. */
export function pruneInactiveChoiceBranches(treeRoot, checkedPaths) {
  if (!treeRoot) return
  const stack = [treeRoot]
  while (stack.length > 0) {
    const node = stack.pop()
    if (node._isChoiceGroup) {
      for (const alt of node.children || []) {
        if (isChoiceAlternativeSelected(node, alt, checkedPaths)) continue
        for (const p of [...checkedPaths]) {
          if (p === alt.path || p.startsWith(`${alt.path}.`)) {
            checkedPaths.delete(p)
          }
        }
      }
    }
    const children = node.children
    if (children) {
      for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
    }
  }
}

function hasCheckedDescendant(node, checkedPaths) {
  const prefix = `${node.path}.`
  for (const p of checkedPaths) {
    if (p.startsWith(prefix)) return true
  }
  return false
}

function addImpliedAncestorPaths(treeRoot, checkedPaths) {
  walkTree(treeRoot, (n) => {
    if (n.isGroupLabel || n.required || !isInActiveBranch(n, treeRoot, checkedPaths)) return
    if (hasCheckedDescendant(n, checkedPaths)) checkedPaths.add(n.path)
  })
}

export function pruneOrphanPaths(treeRoot, checkedPaths) {
  if (!treeRoot) return
  for (const path of [...checkedPaths]) {
    const node = findNodeByPath(path, treeRoot)
    if (!node || !isInActiveBranch(node, treeRoot, checkedPaths)) {
      checkedPaths.delete(path)
    }
  }
}

export function syncCheckedFromPaths(treeRoot, checkedPaths) {
  if (!treeRoot) return
  pruneOrphanPaths(treeRoot, checkedPaths)
  enforceChoiceExclusivity(treeRoot, checkedPaths)
  pruneInactiveChoiceBranches(treeRoot, checkedPaths)
  walkTree(treeRoot, (n) => {
    const active = isInActiveBranch(n, treeRoot, checkedPaths)
    if (active && n.required) {
      checkedPaths.add(n.path)
    } else if (!active) {
      checkedPaths.delete(n.path)
    }
  })
  addImpliedAncestorPaths(treeRoot, checkedPaths)
  enforceChoiceExclusivity(treeRoot, checkedPaths)
  pruneInactiveChoiceBranches(treeRoot, checkedPaths)
  walkTree(treeRoot, (n) => {
    const active = isInActiveBranch(n, treeRoot, checkedPaths)
    n.locked = active && n.required
    n.checked = active && (n.required || checkedPaths.has(n.path))
  })
}

export function ensureAncestorPaths(path, checkedPaths, treeRoot) {
  let current = findNodeByPath(path, treeRoot)
  while (current) {
    const parent = findParentNode(current.path, treeRoot)
    if (!parent) break
    if (!parent.required) {
      checkedPaths.add(parent.path)
    }
    current = parent
  }
}

export function addCheckedAncestors(targetSet, node, treeRoot) {
  let current = node
  while (current) {
    const parent = findParentNode(current.path, treeRoot)
    if (!parent) break
    if (!parent.required) targetSet.add(parent.path)
    current = parent
  }
}

export function expandAncestorsOfChecked(checkedPaths, treeRoot) {
  if (!treeRoot || !checkedPaths.size) return
  // Build nodeMap and parentMap in a single O(N) pass so ancestor traversal
  // is O(1) per step instead of O(N) findParentNode on every step.
  const nodeMap = new Map()
  const parentMap = new Map()
  const stack = [treeRoot]
  while (stack.length > 0) {
    const node = stack.pop()
    nodeMap.set(node.path, node)
    for (const child of node.children || []) {
      parentMap.set(child.path, node)
      stack.push(child)
    }
  }
  for (const path of checkedPaths) {
    let node = nodeMap.get(path)
    while (node) {
      node.expanded = true
      node = parentMap.get(node.path)
    }
  }
}

export function toggleCheckPath(path, checkedPaths, treeRoot) {
  const node = findNodeByPath(path, treeRoot)
  if (!node || node.locked) return false

  if (checkedPaths.has(node.path)) {
    removePathAndDescendants(node.path, checkedPaths, treeRoot)
  } else {
    checkedPaths.add(node.path)
    ensureAncestorPaths(path, checkedPaths, treeRoot)
    const choiceGroup = findChoiceGroupAncestor(node, treeRoot)
    if (choiceGroup) {
      const selectedAlt = findChoiceAlternative(choiceGroup, node)
      for (const sibling of choiceGroup.children) {
        if (selectedAlt && sibling.path === selectedAlt.path) continue
        removePathAndDescendants(sibling.path, checkedPaths, treeRoot)
      }
    }
  }
  return true
}
