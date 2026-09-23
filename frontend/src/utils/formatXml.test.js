import { describe, expect, it } from 'vitest'
import { formatXml, formatXmlIndentAttributes } from './formatXml'

describe('formatXmlIndentAttributes', () => {
  it('puts every attribute on its own line and keeps > on the last one', () => {
    const result = formatXmlIndentAttributes(
      '<root><PayDoc id="1" kind="payment"><Amount>10</Amount></PayDoc></root>',
    )
    expect(result).toMatch(/<PayDoc\n\s+id="1"\n\s+kind="payment">/)
    expect(result).not.toMatch(/<PayDoc[^\n>]*id=/)
  })

  it('breaks a single attribute onto the next line', () => {
    const result = formatXmlIndentAttributes('<root><Only id="1">x</Only></root>')
    expect(result).toMatch(/<Only\n\s+id="1">/)
  })

  it('keeps a self-closing slash on the last attribute line', () => {
    const result = formatXmlIndentAttributes('<root><Empty id="x"/></root>')
    expect(result).toMatch(/<Empty\n\s+id="x" \/>/)
  })

  it('keeps > that sits inside an attribute value', () => {
    const result = formatXmlIndentAttributes('<root><tag note="a>b" id="1">x</tag></root>')
    expect(result).toMatch(/<tag\n\s+note="a>b"\n\s+id="1">/)
  })

  it('does not rewrite tags inside comments or CDATA', () => {
    const commented = formatXmlIndentAttributes(
      '<root><!-- <tag a="1"> --><child b="2">t</child></root>',
    )
    expect(commented).toContain('<!-- <tag a="1"> -->')
    expect(commented).toMatch(/<child\n\s+b="2">/)

    const cdata = formatXmlIndentAttributes('<root><![CDATA[<tag a="1">]]></root>')
    expect(cdata).toContain('<![CDATA[<tag a="1">]]>')
  })

  it('leaves the default formatter unchanged for tags without attributes', () => {
    const xml = '<root><child>text</child></root>'
    expect(formatXmlIndentAttributes(xml)).toBe(formatXml(xml))
  })

  it('is stable when applied twice', () => {
    const xml = '<root><PayDoc id="1" kind="payment"/></root>'
    const once = formatXmlIndentAttributes(xml)
    expect(formatXmlIndentAttributes(once)).toBe(once)
  })

  it('returns empty input unchanged', () => {
    expect(formatXmlIndentAttributes('')).toBe('')
    expect(formatXmlIndentAttributes('   ')).toBe('   ')
  })
})
