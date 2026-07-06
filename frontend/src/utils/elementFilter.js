export const ELEMENT_FILTER_MIN_QUERY = 2
export const ELEMENT_FILTER_DEFAULT_LIMIT = 50
export const ELEMENT_FILTER_MAX_DISPLAY = 100

/** Lowercase key: spaces, hyphens and underscores are equivalent. */
export function normalizeElementSearchKey(text) {
  return (text || '').toLowerCase().replace(/[\s_\-]+/g, '')
}

/** Lower rank = better match (exact, then prefix, then substring). */
function elementMatchRank(el, key) {
  const nk = normalizeElementSearchKey(el)
  if (nk === key) return 0
  if (nk.startsWith(key)) return 1
  return 2
}

/**
 * Map typed query to a DTD element name when the match is unambiguous.
 * @param {string} query
 * @param {string[]} elements
 * @returns {string}
 */
export function resolveElementName(query, elements) {
  const trimmed = (query || '').trim()
  if (!trimmed) return ''

  const list = elements || []
  if (list.includes(trimmed)) return trimmed

  const key = normalizeElementSearchKey(trimmed)
  if (!key) return trimmed

  const exact = list.filter((el) => normalizeElementSearchKey(el) === key)
  if (exact.length === 1) return exact[0]

  const partial = list.filter((el) => normalizeElementSearchKey(el).includes(key))
  if (partial.length === 1) return partial[0]

  return trimmed
}

/**
 * Flat substring filter for DTD element names (case-insensitive;
 * spaces in query match hyphens/underscores in element names).
 * @param {string[]} elements
 * @param {string} query
 * @returns {{ matches: string[], total: number }}
 */
export function filterElements(elements, query) {
  const list = elements || []
  const q = (query || '').trim()

  if (!q || q.length < ELEMENT_FILTER_MIN_QUERY) {
    return {
      matches: list.slice(0, ELEMENT_FILTER_DEFAULT_LIMIT),
      total: list.length,
    }
  }

  const key = normalizeElementSearchKey(q)
  const allMatches = list
    .map((el, index) => ({ el, index }))
    .filter(({ el }) => normalizeElementSearchKey(el).includes(key))
    .sort((a, b) => {
      const rankDiff = elementMatchRank(a.el, key) - elementMatchRank(b.el, key)
      if (rankDiff !== 0) return rankDiff
      return a.index - b.index
    })
    .map(({ el }) => el)
  return {
    matches: allMatches.slice(0, ELEMENT_FILTER_MAX_DISPLAY),
    total: allMatches.length,
  }
}
