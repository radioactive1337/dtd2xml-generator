import { resolveChildTreePaths } from '../dtdTreeNavigation'
import { normalizeTreePath } from '../xmlPaths'

export const GROUP_LABEL_MAX = 72

export function isRequiredQuantifier(q) {
  return q !== '?' && q !== '*'
}

export function isChoiceChildRequired(parentKind, childQuantifier) {
  if (parentKind === 'CHOICE') return false
  return isRequiredQuantifier(childQuantifier || '')
}

export function formatGroupMemberLabel(child) {
  if (child.kind === 'REF') {
    const q = child.quantifier || ''
    return `${child.ref}${q}`
  }
  if (child.kind === 'SEQUENCE' || child.kind === 'CHOICE') {
    return formatGroupLabel(child)
  }
  return child.kind.toLowerCase()
}

export function formatGroupLabel(model) {
  const joiner = model.kind === 'CHOICE' ? ' | ' : ', '
  const inner = (model.children || []).map(formatGroupMemberLabel).join(joiner)
  const label = `(${inner})`
  if (label.length <= GROUP_LABEL_MAX) return label
  return `${label.slice(0, GROUP_LABEL_MAX - 1)}…`
}

export function nodeDisplayName(name, model) {
  if (name.startsWith('group-') && (model.kind === 'SEQUENCE' || model.kind === 'CHOICE')) {
    return formatGroupLabel(model)
  }
  return name
}

/** Unwrap SEQUENCE(CHOICE) so the REF parent becomes the CHOICE container. */
export function normalizeContentModelForTree(model) {
  if (
    model?.kind === 'SEQUENCE'
    && model.children?.length === 1
    && model.children[0].kind === 'CHOICE'
  ) {
    return model.children[0]
  }
  return model
}

export function createNodeIdFactory() {
  let counter = 0
  return () => `node-${counter++}`
}

export function buildNodeFromModel({
  name,
  model,
  path,
  depth,
  required,
  elementPath = null,
  rootElement,
  nextId,
  onRequiredRootCheck,
}) {
  const elPath = elementPath ?? path
  const quantifier = model.quantifier || ''
  const isGroup = model.kind === 'SEQUENCE' || model.kind === 'CHOICE'
  const nodeRequired = isGroup
    ? required || isRequiredQuantifier(quantifier)
    : required
  const node = {
    id: nextId(),
    name,
    displayName: nodeDisplayName(name, model),
    isGroupLabel: name.startsWith('group-'),
    path,
    depth,
    quantifier,
    required: nodeRequired,
    locked: false,
    checked: nodeRequired,
    expanded: false,
    hasChildren: false,
    children: [],
    _refName: null,
    _loaded: false,
    _isChoiceGroup: model.kind === 'CHOICE',
  }

  if (nodeRequired && path === rootElement) {
    onRequiredRootCheck?.(path)
  }

  if (model.kind === 'REF') {
    if (name === model.ref) {
      node.hasChildren = true
      node._refName = model.ref
    } else {
      const childPath = `${path}.${model.ref}`
      const childNode = buildNodeFromModel({
        name: model.ref,
        model,
        path: childPath,
        depth: depth + 1,
        required: isRequiredQuantifier(model.quantifier || ''),
        rootElement,
        nextId,
        onRequiredRootCheck,
      })
      node.hasChildren = true
      node.children = [childNode]
      node._loaded = true
    }
  } else if (model.kind === 'SEQUENCE' || model.kind === 'CHOICE') {
    node.hasChildren = (model.children || []).length > 0
    node.children = (model.children || []).map((child, idx) => {
      const { childPath, elementPath: childElementPath } = resolveChildTreePaths(
        path,
        elPath,
        model.kind,
        child,
        idx,
      )
      return buildNodeFromModel({
        name: child.kind === 'REF' ? child.ref : `group-${idx}`,
        model: child,
        path: childPath,
        depth: depth + 1,
        required: isChoiceChildRequired(model.kind, child.quantifier),
        elementPath: childElementPath,
        rootElement,
        nextId,
        onRequiredRootCheck,
      })
    })
    node._loaded = true
  }

  return node
}

export function buildChildrenFromModel({ model, parentPath, depth, rootElement, nextId, onRequiredRootCheck }) {
  if (model.kind === 'REF') {
    const childPath = `${parentPath}.${model.ref}`
    return [
      buildNodeFromModel({
        name: model.ref,
        model,
        path: childPath,
        depth,
        required: isRequiredQuantifier(model.quantifier || ''),
        rootElement,
        nextId,
        onRequiredRootCheck,
      }),
    ]
  }
  if (model.kind === 'SEQUENCE' || model.kind === 'CHOICE') {
    return (model.children || []).map((child, idx) => {
      const { childPath, elementPath: childElementPath } = resolveChildTreePaths(
        parentPath,
        parentPath,
        model.kind,
        child,
        idx,
      )
      return buildNodeFromModel({
        name: child.kind === 'REF' ? child.ref : `group-${idx}`,
        model: child,
        path: childPath,
        depth,
        required: isChoiceChildRequired(model.kind, child.quantifier),
        elementPath: childElementPath,
        rootElement,
        nextId,
        onRequiredRootCheck,
      })
    })
  }
  return []
}

/** Apply lazy-loaded content model; mark REF parent as CHOICE container when needed. */
export function applyLoadedChildren(node, contentModel, options) {
  const model = normalizeContentModelForTree(contentModel)
  node.children = buildChildrenFromModel({
    model,
    parentPath: node.path,
    depth: node.depth + 1,
    ...options,
  })
  node._loaded = true
  node.hasChildren = node.children.length > 0
  node._isChoiceGroup = model.kind === 'CHOICE'
}

export function findNodeByPath(path, node) {
  if (!node) return null
  if (node.path === path) return node
  for (const child of node.children || []) {
    const found = findNodeByPath(path, child)
    if (found) return found
  }
  return null
}

export function findParentNode(path, node) {
  if (!node) return null
  for (const child of node.children || []) {
    if (child.path === path) return node
    const found = findParentNode(path, child)
    if (found) return found
  }
  return null
}

export function flattenVisible(node) {
  const result = []
  if (!node) return result
  function walk(n) {
    result.push(n)
    if (n.expanded) {
      for (const child of n.children || []) walk(child)
    }
  }
  walk(node)
  return result
}

export function walkTree(node, fn) {
  if (!node) return
  fn(node)
  for (const child of node.children || []) walkTree(child, fn)
}

export function collectDescendantPaths(node) {
  const paths = []
  for (const child of node.children || []) {
    paths.push(child.path)
    paths.push(...collectDescendantPaths(child))
  }
  return paths
}

export function skipGroupLabelParent(node, treeRoot) {
  let parent = findParentNode(node.path, treeRoot)
  while (parent?.isGroupLabel && !parent._isChoiceGroup) {
    parent = findParentNode(parent.path, treeRoot)
  }
  return parent
}

export function findChoiceGroupAncestor(node, treeRoot) {
  let current = node
  while (current) {
    const parent = skipGroupLabelParent(current, treeRoot)
    if (!parent) break
    if (parent._isChoiceGroup) return parent
    current = parent
  }
  return null
}

export function findChoiceAlternative(choiceGroup, node) {
  const nodePath = node.path
  for (const alt of choiceGroup.children || []) {
    if (nodePath === alt.path || nodePath.startsWith(`${alt.path}.`)) {
      return alt
    }
  }
  return null
}

export function findNodesForElementPath(elPath, node, results = []) {
  if (!node) return results
  if (!node.isGroupLabel && normalizeTreePath(node.path) === elPath) {
    results.push(node)
  }
  for (const child of node.children || []) {
    findNodesForElementPath(elPath, child, results)
  }
  return results
}

