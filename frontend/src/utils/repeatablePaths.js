import { getElementTree } from '../api/dtd'
import { resolveChildTreePaths } from './dtdTreeNavigation'
import { formatGroupLabel } from './dtdTree/model'
import { normalizeTreePath } from './xmlPaths'

function pushRepeatable(items, seen, { path, name, quantifier, isGroup = false }) {
  const normalized = normalizeTreePath(path)
  if (seen.has(normalized)) return
  seen.add(normalized)
  items.push({ path: normalized, name, quantifier, isGroup })
}

function collectFromModel(model, treePath, elementPath, items, seen) {
  if (!model) return

  if (model.kind === 'REF') {
    const q = model.quantifier || ''
    if (q === '+' || q === '*') {
      const repeatPath = treePath === elementPath
        ? `${elementPath}.${model.ref}`
        : elementPath
      pushRepeatable(items, seen, {
        path: repeatPath,
        name: model.ref,
        quantifier: q,
      })
    }
    return
  }

  if (model.kind === 'SEQUENCE' || model.kind === 'CHOICE') {
    const q = model.quantifier || ''
    if (q === '+' || q === '*') {
      pushRepeatable(items, seen, {
        path: treePath,
        name: formatGroupLabel(model),
        quantifier: q,
        isGroup: true,
      })
    }

    for (let idx = 0; idx < (model.children || []).length; idx++) {
      const child = model.children[idx]
      const { childPath, elementPath: childElPath } = resolveChildTreePaths(
        treePath,
        elementPath,
        model.kind,
        child,
        idx,
      )

      if (child.kind === 'REF') {
        const cq = child.quantifier || ''
        if (cq === '+' || cq === '*') {
          pushRepeatable(items, seen, {
            path: childElPath,
            name: child.ref,
            quantifier: cq,
          })
        }
      } else if (child.kind === 'SEQUENCE' || child.kind === 'CHOICE') {
        collectFromModel(child, childPath, childElPath, items, seen)
      }
    }
  }
}

/**
 * Load all DTD paths with + or * quantifiers under rootElement (BFS via element tree API).
 * @returns {Promise<Array<{ path: string, name: string, quantifier: string, isGroup?: boolean }>>}
 */
export async function loadRepeatablePaths(schemaId, rootElement) {
  const root = rootElement?.trim()
  if (!schemaId || !root) return []

  const items = []
  const seen = new Set()
  const expanded = new Set()
  const cache = new Map()

  async function loadModel(elementName) {
    if (!cache.has(elementName)) {
      const data = await getElementTree(schemaId, elementName)
      cache.set(elementName, data?.content_model ?? null)
    }
    return cache.get(elementName)
  }

  const queue = [{ refToLoad: root, treePath: root, elementPath: root }]

  while (queue.length > 0) {
    const state = queue.shift()
    if (expanded.has(state.treePath)) continue
    expanded.add(state.treePath)

    const model = await loadModel(state.refToLoad)
    if (!model) continue

    collectFromModel(model, state.treePath, state.elementPath, items, seen)

    if (model.kind === 'REF') {
      const childPath = `${state.treePath}.${model.ref}`
      if (!expanded.has(childPath)) {
        queue.push({
          refToLoad: model.ref,
          treePath: childPath,
          elementPath: childPath,
        })
      }
      continue
    }

    if (model.kind === 'SEQUENCE' || model.kind === 'CHOICE') {
      for (let idx = 0; idx < (model.children || []).length; idx++) {
        const child = model.children[idx]
        const { childPath, elementPath: childElPath } = resolveChildTreePaths(
          state.treePath,
          state.elementPath,
          model.kind,
          child,
          idx,
        )
        if (child.kind === 'REF' && !expanded.has(childPath)) {
          queue.push({
            refToLoad: child.ref,
            treePath: childPath,
            elementPath: childElPath,
          })
        } else if (child.kind === 'SEQUENCE' || child.kind === 'CHOICE') {
          queue.push({
            refToLoad: state.refToLoad,
            treePath: childPath,
            elementPath: childElPath,
          })
        }
      }
    }
  }

  return items.sort((a, b) => a.path.localeCompare(b.path))
}

export function formatRepeatableLabel(item) {
  if (!item) return ''
  const suffix = item.isGroup ? '' : item.quantifier
  return `${item.name}${suffix} — ${item.path}`
}
