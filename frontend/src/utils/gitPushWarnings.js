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
