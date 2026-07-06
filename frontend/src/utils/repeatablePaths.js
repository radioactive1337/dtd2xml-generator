import { getElementTree } from '../api/dtd'
import { resolveChildTreePaths } from './dtdTreeNavigation'
import { formatGroupLabel } from './dtdTree/model'
import { normalizeTreePath } from './xmlPaths'

const MAX_SCAN_NODES = 2000

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

  const queue = [{
    refToLoad: root,
    treePath: root,
    elementPath: root,
    ancestry: new Set([root]),
  }]
  let processed = 0
  let queueIndex = 0

  while (queueIndex < queue.length && processed < MAX_SCAN_NODES) {
    const state = queue[queueIndex++]
    if (expanded.has(state.treePath)) continue
    expanded.add(state.treePath)
    processed += 1

    // Keep large schemas from monopolizing the UI thread while this list is built.
    if (processed % 25 === 0) {
      await new Promise((resolve) => setTimeout(resolve, 0))
    }

    const model = await loadModel(state.refToLoad)
    if (!model) continue

    collectFromModel(model, state.treePath, state.elementPath, items, seen)

    if (model.kind === 'REF') {
      const childPath = `${state.treePath}.${model.ref}`
      if (!expanded.has(childPath) && !state.ancestry.has(model.ref)) {
        queue.push({
          refToLoad: model.ref,
          treePath: childPath,
          elementPath: childPath,
          ancestry: new Set([...state.ancestry, model.ref]),
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
          if (state.ancestry.has(child.ref)) continue
          queue.push({
            refToLoad: child.ref,
            treePath: childPath,
            elementPath: childElPath,
            ancestry: new Set([...state.ancestry, child.ref]),
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
