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

// Stop processing after this many elements so a huge XML cannot OOM the browser.
// Tree-sync only needs structural coverage; 10 000 nodes is more than enough.
const MAX_WALK_NODES = 10_000

function collectElementPaths(doc) {
  const root = doc.documentElement
  if (!root) return { rootTag: '', elementPaths: [] }

  const rootTag = localTagName(root)

  // Use an explicit stack so we never blow the JS call stack on deeply nested XML.
  // Deduplicate into a Set during collection to keep peak memory minimal.
  const seen = new Set()
  const stack = [[root, rootTag]]

  while (stack.length > 0) {
    if (seen.size >= MAX_WALK_NODES) break

    const [el, pathToEl] = stack.pop()
    seen.add(pathToEl)

    const children = el.children
    const tagCounts = {}
    for (let i = 0; i < children.length; i++) {
      const childTag = localTagName(children[i])
      if (childTag) tagCounts[childTag] = (tagCounts[childTag] || 0) + 1
    }

    // Push children in reverse order so the stack processes them left-to-right.
    const tagIndices = {}
    const toQueue = []
    for (let i = 0; i < children.length; i++) {
      const child = children[i]
      const childTag = localTagName(child)
      if (!childTag) continue
      const idx = tagIndices[childTag] || 0
      tagIndices[childTag] = idx + 1
      const segment = tagCounts[childTag] > 1 ? `${childTag}[${idx}]` : childTag
      toQueue.push([child, `${pathToEl}.${segment}`])
    }
    for (let i = toQueue.length - 1; i >= 0; i--) {
      stack.push(toQueue[i])
    }
  }

  return { rootTag, elementPaths: [...seen] }
}

// XML larger than this is not walked for tree-sync — DOMParser alone would
// materialise the full tree in memory and risk an OOM on large documents.
const MAX_PARSE_BYTES = 4 * 1024 * 1024 // 4 MB

/**
 * Parse XML text and return the document root tag plus dot-separated element paths.
 * Returns null when the text is empty, not well-formed XML, or exceeds the size
 * threshold (tree-sync is skipped for very large documents).
 *
 * @param {string} xmlText
 * @param {{ skipFormat?: boolean }} [options]
 *   skipFormat — skip the xml-formatter fallback pass (use for live editor input
 *   where malformed XML is expected during typing and re-formatting never helps).
 */
export function extractXmlElementPaths(xmlText, { skipFormat = false } = {}) {
  const trimmed = normalizeXmlInput(xmlText)
  if (!trimmed) return null

  // Bail out early to avoid OOM on very large files.
  if (trimmed.length > MAX_PARSE_BYTES) return null

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
