import xmlFormat from 'xml-formatter'

const INDENT = '  '

export function formatXml(xml) {
  if (!xml?.trim()) return xml || ''
  return xmlFormat(xml, {
    indentation: INDENT,
    lineSeparator: '\n',
    throwOnFailure: false,
  })
}

export function formatXmlIndentAttributes(xml) {
  if (!xml?.trim()) return xml || ''
  return indentAttributes(formatXml(xml))
}

export function registerXmlFormatter(monaco) {
  monaco.languages.registerDocumentFormattingEditProvider('xml', {
    async provideDocumentFormattingEdits(model) {
      const source = model.getValue()
      const formatted = formatXml(source)
      if (formatted === source) return []
      return [{ range: model.getFullModelRange(), text: formatted }]
    },
  })
}

function indentAttributes(xml) {
  let result = ''
  let index = 0
  while (index < xml.length) {
    if (xml[index] !== '<') {
      result += xml[index]
      index += 1
      continue
    }
    const end = markupEnd(xml, index)
    const chunk = xml.slice(index, end)
    result += shouldRewriteTag(chunk) ? rewriteStartTag(chunk, result) : chunk
    index = end
  }
  return result
}

function shouldRewriteTag(tag) {
  return tag.startsWith('<')
    && !tag.startsWith('</')
    && !tag.startsWith('<?')
    && !tag.startsWith('<!')
}

function markupEnd(xml, start) {
  if (xml.startsWith('<!--', start)) {
    const end = xml.indexOf('-->', start + 4)
    return end === -1 ? xml.length : end + 3
  }
  if (xml.startsWith('<![CDATA[', start)) {
    const end = xml.indexOf(']]>', start + 9)
    return end === -1 ? xml.length : end + 3
  }
  if (xml.startsWith('<?', start)) {
    const end = xml.indexOf('?>', start + 2)
    return end === -1 ? xml.length : end + 2
  }
  return scanToTagEnd(xml, start)
}

function scanToTagEnd(xml, start) {
  let quote = ''
  let brackets = 0
  for (let i = start; i < xml.length; i += 1) {
    const ch = xml[i]
    if (quote) {
      if (ch === quote) quote = ''
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      continue
    }
    if (ch === '[') {
      brackets += 1
      continue
    }
    if (ch === ']' && brackets > 0) {
      brackets -= 1
      continue
    }
    if (ch === '>' && brackets === 0) return i + 1
  }
  return xml.length
}

function rewriteStartTag(tag, written) {
  const parsed = parseStartTag(tag)
  if (!parsed || parsed.attrs.length === 0) return tag
  const attrIndent = lineIndent(written) + INDENT
  const close = parsed.selfClosing ? ' />' : '>'
  const lines = parsed.attrs.map((attr, attrIndex) => {
    const suffix = attrIndex === parsed.attrs.length - 1 ? close : ''
    return `${attrIndent}${attr}${suffix}`
  })
  return `<${parsed.name}\n${lines.join('\n')}`
}

function lineIndent(written) {
  const breakAt = written.lastIndexOf('\n')
  const line = breakAt === -1 ? written : written.slice(breakAt + 1)
  const match = /^[ \t]*/.exec(line)
  return match ? match[0] : ''
}

function parseStartTag(tag) {
  if (!tag.startsWith('<') || !tag.endsWith('>')) return null
  const name = readToken(tag, 1)
  if (!name) return null
  const attrs = []
  let index = name.end
  while (index < tag.length) {
    while (index < tag.length && /\s/.test(tag[index])) index += 1
    if (index >= tag.length || tag[index] === '>') break
    if (tag[index] === '/' && tag[index + 1] === '>') {
      return { name: name.value, attrs, selfClosing: true }
    }
    const attrName = readToken(tag, index)
    if (!attrName) return null
    let cursor = attrName.end
    while (cursor < tag.length && /\s/.test(tag[cursor])) cursor += 1
    if (tag[cursor] !== '=') return null
    cursor += 1
    while (cursor < tag.length && /\s/.test(tag[cursor])) cursor += 1
    const quote = tag[cursor]
    if (quote !== '"' && quote !== "'") return null
    const valueEnd = tag.indexOf(quote, cursor + 1)
    if (valueEnd === -1) return null
    attrs.push(tag.slice(attrName.start, valueEnd + 1))
    index = valueEnd + 1
  }
  return { name: name.value, attrs, selfClosing: false }
}

function readToken(source, start) {
  let index = start
  while (index < source.length && !/[\s=/>]/.test(source[index])) index += 1
  if (index === start) return null
  return { value: source.slice(start, index), start, end: index }
}
