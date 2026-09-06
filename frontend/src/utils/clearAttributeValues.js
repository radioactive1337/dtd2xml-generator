/** Blank attribute values, then restore DTD-declared defaults. */

import { dtdLocalName } from './dtdSchema'

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

function indexAttributeDefaults(attributeDefaults) {
  if (!attributeDefaults) return {}
  const indexed = { ...attributeDefaults }
  for (const [name, attrs] of Object.entries(attributeDefaults)) {
    const local = dtdLocalName(name)
    if (local !== name && indexed[local] == null) indexed[local] = attrs
  }
  return indexed
}

function lookupDtdDefault(indexed, tagName, attrName) {
  if (!indexed || !tagName || !attrName) return undefined
  const elem = indexed[tagName] || indexed[dtdLocalName(tagName)]
  if (!elem) return undefined
  if (Object.prototype.hasOwnProperty.call(elem, attrName)) return elem[attrName]
  const localAttr = dtdLocalName(attrName)
  if (localAttr !== attrName && Object.prototype.hasOwnProperty.call(elem, localAttr)) {
    return elem[localAttr]
  }
  return undefined
}

function quoteAttrValue(value, quote) {
  const escaped = String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(quote === '"' ? /"/g : /'/g, quote === '"' ? '&quot;' : '&apos;')
  return `${quote}${escaped}${quote}`
}

/**
 * @param {string} text
 * @param {{ keepCsName?: boolean, prefix?: string, attributeDefaults?: Record<string, Record<string, string>> }} [options]
 *   keepCsName — leave `name` on `cs:*` tags (default true).
 *   prefix — text immediately before `text` (open-tag lookbehind).
 *   attributeDefaults — element → attr → DTD default (`currency CDATA "RUB"`).
 */
export function clearAttributeValues(text, options = {}) {
  const keepCsName = options.keepCsName !== false
  const prefix = options.prefix || ''
  const attributeDefaults = indexAttributeDefaults(options.attributeDefaults)
  const full = prefix + text

  return text.replace(ATTR_RE, (match, name, eq, quoted, offset) => {
    const tagName = tagNameAt(full, prefix.length + offset)
    if (shouldKeepAttribute(tagName, name, keepCsName)) return match
    const dtdDefault = lookupDtdDefault(attributeDefaults, tagName, name)
    if (dtdDefault != null) return `${name}${eq}${quoteAttrValue(dtdDefault, quoted[0])}`
    return `${name}${eq}${quoted[0]}${quoted[0]}`
  })
}
