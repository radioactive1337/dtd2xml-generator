import { resolveChildTreePaths } from '../dtdTreeNavigation'
import { normalizeTreePath, stripPathIndex } from '../xmlPaths'

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
  } else if (model.kind === 'ANY') {
    node._isAnyContainer = true
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

/** Direct child element names under parentPath found in pasted XML paths. */
export function collectDirectChildNamesFromXmlPaths(parentPath, elementPaths) {
  const parentNorm = normalizeTreePath(parentPath || '')
  const prefix = parentNorm ? `${parentNorm}.` : ''
  const names = new Set()

  for (const rawPath of elementPaths || []) {
    const norm = normalizeTreePath(rawPath)
    if (parentNorm) {
      if (norm !== parentNorm && !norm.startsWith(prefix)) continue
    }
    const rest = parentNorm ? norm.slice(prefix.length) : norm
    if (!rest) continue
    const name = stripPathIndex(rest.split('.')[0])
    if (name) names.add(name)
  }

  return [...names].sort()
}

/** Build tree children for ANY content from element paths in a pasted XML document. */
export function injectXmlChildrenIntoAnyNode(node, elementPaths, options) {
  const childNames = collectDirectChildNamesFromXmlPaths(node.path, elementPaths)
  node.children = childNames.map((childName) => {
    const childPath = node.path ? `${node.path}.${childName}` : childName
    const childNode = buildNodeFromModel({
      name: childName,
      model: { kind: 'REF', ref: childName },
      path: childPath,
      depth: node.depth + 1,
      required: false,
      elementPath: childPath,
      ...options,
    })
    const hasDeeperPaths = (elementPaths || []).some((p) => {
      const norm = normalizeTreePath(p)
      return norm !== childPath && norm.startsWith(`${childPath}.`)
    })
    if (hasDeeperPaths) {
      childNode.hasChildren = true
    }
    return childNode
  })
  node._isAnyContainer = true
  node._loaded = true
  node.hasChildren = node.children.length > 0
  node._isChoiceGroup = false
}

/** Apply lazy-loaded content model; mark REF parent as CHOICE container when needed. */
export function applyLoadedChildren(node, contentModel, options) {
  const model = normalizeContentModelForTree(contentModel)
  if (model.kind === 'ANY') {
    node._isAnyContainer = true
    if (options.xmlElementPaths?.length) {
      injectXmlChildrenIntoAnyNode(node, options.xmlElementPaths, options)
    } else {
      node.children = []
      node._loaded = true
      node.hasChildren = false
      node._isChoiceGroup = false
    }
    return
  }
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

export function findNodeByPath(path, root) {
  if (!root) return null
  const stack = [root]
  while (stack.length > 0) {
    const node = stack.pop()
    if (node.path === path) return node
    const children = node.children
    if (children) {
      for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
    }
  }
  return null
}

export function findParentNode(path, root) {
  if (!root) return null
  const stack = [root]
  while (stack.length > 0) {
    const node = stack.pop()
    const children = node.children
    if (children) {
      for (let i = children.length - 1; i >= 0; i--) {
        const child = children[i]
        if (child.path === path) return node
        stack.push(child)
      }
    }
  }
  return null
}

export function flattenVisible(root) {
  const result = []
  if (!root) return result
  const stack = [root]
  while (stack.length > 0) {
    const node = stack.pop()
    result.push(node)
    if (node.expanded) {
      const children = node.children
      if (children) {
        for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
      }
    }
  }
  return result
}

/** Build path→node and path→parent maps in a single O(N) tree pass. */
export function buildNodeAndParentMaps(root) {
  const nodeMap = new Map()
  const parentMap = new Map()
  if (!root) return { nodeMap, parentMap }
  const stack = [root]
  while (stack.length > 0) {
    const node = stack.pop()
    nodeMap.set(node.path, node)
    for (const child of node.children || []) {
      parentMap.set(child.path, node)
      stack.push(child)
    }
  }
  return { nodeMap, parentMap }
}

export function walkTree(root, fn) {
  if (!root) return
  const stack = [root]
  while (stack.length > 0) {
    const node = stack.pop()
    fn(node)
    const children = node.children
    if (children) {
      for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
    }
  }
}

export function collectDescendantPaths(node) {
  const paths = []
  const stack = [...(node.children || [])]
  while (stack.length > 0) {
    const current = stack.pop()
    paths.push(current.path)
    const children = current.children
    if (children) {
      for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
    }
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

export function findNodesForElementPath(elPath, root) {
  const results = []
  if (!root) return results
  const stack = [root]
  while (stack.length > 0) {
    const node = stack.pop()
    if (!node.isGroupLabel && normalizeTreePath(node.path) === elPath) {
      results.push(node)
    }
    const children = node.children
    if (children) {
      for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
    }
  }
  return results
}

