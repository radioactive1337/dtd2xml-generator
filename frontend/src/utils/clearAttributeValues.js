/** Blank attribute values in the given text: name="value" -> name="". */

const ATTR_RE = /([\w:.-]+)(\s*=\s*)("[^"]*"|'[^']*')/g
const OPEN_TAG_NAME_RE = /^<([A-Za-z_][\w:.-]*)/

/**
 * If `beforeText` ends inside an open tag, return that tag from `<` onward.
 * Used so a mid-tag selection still knows the element name.
 */
export function openTagPrefix(beforeText) {
  if (!beforeText) return ''
  const lastLt = beforeText.lastIndexOf('<')
  if (lastLt === -1) return ''
  const lastGt = beforeText.lastIndexOf('>')
  if (lastGt > lastLt) return ''
  return beforeText.slice(lastLt)
}

function tagNameAt(full, offset) {
  const lastLt = full.lastIndexOf('<', offset - 1)
  if (lastLt === -1) return ''
  const lastGt = full.lastIndexOf('>', offset - 1)
  if (lastGt > lastLt) return ''
  const match = OPEN_TAG_NAME_RE.exec(full.slice(lastLt))
  return match ? match[1] : ''
}

function shouldKeepAttribute(tagName, attrName, keepCsName) {
  if (attrName === 'xmlns' || attrName.startsWith('xmlns:')) return true
  return keepCsName && attrName === 'name' && tagName.startsWith('cs:')
}

/**
 * @param {string} text
 * @param {{ keepCsName?: boolean, prefix?: string }} [options]
 *   keepCsName — leave `name` on `cs:*` tags (default true).
 *   prefix — text immediately before `text` (open-tag lookbehind).
 */
export function clearAttributeValues(text, options = {}) {
  const keepCsName = options.keepCsName !== false
  const prefix = options.prefix || ''
  const full = prefix + text

  return text.replace(ATTR_RE, (match, name, eq, quoted, offset) => {
    const tagName = tagNameAt(full, prefix.length + offset)
    if (shouldKeepAttribute(tagName, name, keepCsName)) return match
    return `${name}${eq}${quoted[0]}${quoted[0]}`
  })
}
