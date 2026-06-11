function localTagName(el) {
  const raw = el.localName || el.tagName || ''
  return raw.replace(/^[^:]+:/, '')
}

/**
 * Parse XML text and return the document root tag plus dot-separated element paths.
 * Returns null when the text is empty or not well-formed XML.
 */
export function extractXmlElementPaths(xmlText) {
  const trimmed = xmlText?.trim()
  if (!trimmed) return null

  const doc = new DOMParser().parseFromString(trimmed, 'application/xml')
  if (doc.querySelector('parsererror')) return null

  const root = doc.documentElement
  if (!root) return { rootTag: '', elementPaths: [] }

  const rootTag = localTagName(root)
  const elementPaths = []

  function walk(el, path) {
    const tag = localTagName(el)
    if (!tag) return
    const currentPath = path ? `${path}.${tag}` : tag
    elementPaths.push(currentPath)
    for (const child of el.children) {
      walk(child, currentPath)
    }
  }

  walk(root, '')
  return { rootTag, elementPaths }
}

/** Strip UI-only group-N segments so tree paths match element paths. */
export function normalizeTreePath(path) {
  return path.replace(/\.group-\d+(?=\.|$)/g, '')
}

export function inferRootFromElementPaths(paths) {
  if (!paths?.length) return ''
  const first = paths[0]
  return first.includes('.') ? first.split('.')[0] : first
}
