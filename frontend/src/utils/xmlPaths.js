import { formatXml } from './formatXml'
import { resolveElementName } from './elementFilter'

function localTagName(el) {
  const raw = el.localName || el.tagName || ''
  return raw.replace(/^[^:]+:/, '')
}

function normalizeXmlInput(xmlText) {
  return xmlText?.trim()?.replace(/^\uFEFF/, '') ?? ''
}

function parseXmlDocument(xmlText) {
  const trimmed = normalizeXmlInput(xmlText)
  if (!trimmed) return null

  const doc = new DOMParser().parseFromString(trimmed, 'application/xml')
  if (doc.querySelector('parsererror')) return null
  return doc
}

function collectElementPaths(doc) {
  const root = doc.documentElement
  if (!root) return { rootTag: '', elementPaths: [] }

  const rootTag = localTagName(root)
  const elementPaths = []

  function childSegment(tag, index, totalWithTag) {
    if (totalWithTag > 1) return `${tag}[${index}]`
    return tag
  }

  function walk(el, currentPath) {
    const tag = localTagName(el)
    if (!tag) return
    const pathToEl = currentPath || tag
    elementPaths.push(pathToEl)

    const children = [...el.children]
    const tagCounts = {}
    for (const child of children) {
      const childTag = localTagName(child)
      if (!childTag) continue
      tagCounts[childTag] = (tagCounts[childTag] || 0) + 1
    }

    const tagIndices = {}
    for (const child of children) {
      const childTag = localTagName(child)
      if (!childTag) continue
      const idx = tagIndices[childTag] || 0
      tagIndices[childTag] = idx + 1
      const segment = childSegment(childTag, idx, tagCounts[childTag])
      walk(child, `${pathToEl}.${segment}`)
    }
  }

  walk(root, '')
  return { rootTag, elementPaths: [...new Set(elementPaths)] }
}

/**
 * Parse XML text and return the document root tag plus dot-separated element paths.
 * Returns null when the text is empty or not well-formed XML.
 *
 * @param {string} xmlText
 * @param {{ skipFormat?: boolean }} [options]
 *   skipFormat — skip the xml-formatter fallback pass (use for live editor input
 *   where malformed XML is expected during typing and re-formatting never helps).
 */
export function extractXmlElementPaths(xmlText, { skipFormat = false } = {}) {
  const trimmed = normalizeXmlInput(xmlText)
  if (!trimmed) return null

  let doc = parseXmlDocument(trimmed)
  if (!doc && !skipFormat) {
    doc = parseXmlDocument(formatXml(trimmed))
  }
  if (!doc) return null

  return collectElementPaths(doc)
}

/** Strip UI-only group-N segments so tree paths match element paths. */
export function normalizeTreePath(path) {
  return path.replace(/\.group-\d+(?=\.|$)/g, '')
}

/** Strip a trailing [N] sibling index from a path segment or full path's last segment. */
export function stripPathIndex(segment) {
  return (segment || '').replace(/\[\d+\]$/, '')
}

export function inferRootFromElementPaths(paths) {
  if (!paths?.length) return ''
  const first = paths[0]
  return first.includes('.') ? first.split('.')[0] : first
}

export function canonicalizeXmlElementName(name, elements) {
  const segment = name || ''
  const index = segment.match(/\[\d+\]$/)?.[0] || ''
  const base = stripPathIndex(segment)
  const resolved = resolveElementName(base, elements)
  return `${resolved}${index}`
}

export function canonicalizeXmlElementPaths(paths, elements) {
  if (!paths?.length) return []
  return paths.map((path) =>
    path
      .split('.')
      .map((segment) => canonicalizeXmlElementName(segment, elements))
      .join('.'),
  )
}

/**
 * Collapse indexed XML instance paths to structural DTD paths for tree sync.
 * Strips sibling [N] indices and UI-only group-N segments, dedupes, sorts shallow→deep.
 */
export function normalizeElementPathsForTreeSync(paths) {
  const normalized = new Set()
  for (const path of paths || []) {
    if (!path) continue
    const segments = path.split('.').map(stripPathIndex)
    normalized.add(normalizeTreePath(segments.join('.')))
  }
  return [...normalized].sort((a, b) => a.split('.').length - b.split('.').length)
}
