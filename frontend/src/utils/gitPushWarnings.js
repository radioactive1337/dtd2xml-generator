export const PUSH_WARNINGS_REQUIRE_ACK = 'warnings_require_ack'

export function extractPushWarnings(err) {
  const detail = err?.response?.data?.detail
  if (!detail || typeof detail !== 'object') return null
  if (detail.code !== PUSH_WARNINGS_REQUIRE_ACK) return null
  const warnings = Array.isArray(detail.warnings) ? detail.warnings : []
  return {
    warnings,
    warningCount: Number(detail.warning_count) || warnings.length,
    message: detail.message || '',
  }
}

export function formatPushWarningLabel(warning) {
  if (!warning) return ''
  if (typeof warning === 'string') return warning
  const location =
    warning.location ||
    (warning.attr ? `${warning.path || ''}@${warning.attr}` : warning.path || '')
  if (location && warning.message) return `${location} — ${warning.message}`
  return warning.message || location || ''
}

const LOCATION_ITEM = /^(.+@\S+):\s+(.+)$/

export function parsePushFeedbackItem(line) {
  const text = (line || '').trim()
  const match = text.match(LOCATION_ITEM)
  if (match) return { location: match[1], message: match[2] }
  return { location: '', message: text }
}

export function parsePushFeedback(text) {
  const raw = String(text || '')
    .replace(/\r\n/g, '\n')
    .trim()
  if (!raw) return { heading: '', items: [], more: '' }

  const lines = raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  const items = []
  const headingParts = []
  let more = ''

  for (const line of lines) {
    if (line.startsWith('…') || line.startsWith('...')) {
      more = line
      continue
    }
    if (line.startsWith('- ')) {
      items.push(parsePushFeedbackItem(line.slice(2)))
      continue
    }
    headingParts.push(line)
  }

  return {
    heading: headingParts.join(' '),
    items,
    more,
  }
}

