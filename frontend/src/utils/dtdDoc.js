const ALLOWED_TAGS = new Set(['UL', 'OL', 'LI', 'P', 'BR', 'STRONG', 'EM', 'CODE', 'B', 'I'])

function looksLikeHtml(text) {
  return /<[a-z][\s\S]*>/i.test(text)
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function serializeSanitized(node) {
  let html = ''
  for (const child of node.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) {
      html += escapeHtml(child.textContent)
    } else if (child.nodeType === Node.ELEMENT_NODE) {
      const tag = child.tagName
      if (tag === 'BR') {
        html += '<br>'
      } else if (ALLOWED_TAGS.has(tag)) {
        html += `<${tag.toLowerCase()}>${serializeSanitized(child)}</${tag.toLowerCase()}>`
      } else {
        html += serializeSanitized(child)
      }
    }
  }
  return html
}

/** Plain text for tooltips and short previews. */
export function dtdDocPlainText(raw) {
  if (!raw?.trim()) return ''
  const trimmed = raw.trim()
  if (!looksLikeHtml(trimmed)) return trimmed
  if (typeof DOMParser === 'undefined') {
    return trimmed.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
  }
  return new DOMParser().parseFromString(trimmed, 'text/html').body.textContent
    .replace(/\s+/g, ' ')
    .trim()
}

/** One-line preview for dropdowns. */
export function dtdDocPreview(raw, maxLen = 120) {
  const plain = dtdDocPlainText(raw)
  if (plain.length <= maxLen) return plain
  return `${plain.slice(0, maxLen - 1)}…`
}

/** Safe HTML subset for inline doc rendering. */
export function sanitizeDtdDocHtml(raw) {
  if (!raw?.trim()) return ''
  const trimmed = raw.trim()
  if (!looksLikeHtml(trimmed)) {
    return escapeHtml(trimmed).replace(/\n/g, '<br>')
  }
  if (typeof DOMParser === 'undefined') {
    return escapeHtml(dtdDocPlainText(trimmed))
  }
  const doc = new DOMParser().parseFromString(trimmed, 'text/html')
  return serializeSanitized(doc.body).trim()
}
