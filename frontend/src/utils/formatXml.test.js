import { describe, expect, it } from 'vitest'
import { formatXml, formatXmlIndentAttributes } from './formatXml'

describe('formatXmlIndentAttributes', () => {
  it('keeps the first attribute on the tag line and aligns the rest', () => {
    const result = formatXmlIndentAttributes(
      '<root><PayDoc id="1" kind="payment"><Amount>10</Amount></PayDoc></root>',
    )
    expect(result).toMatch(/<PayDoc id="1"\n {10}kind="payment">/)
  })

  it('leaves a single attribute on the tag line', () => {
    const result = formatXmlIndentAttributes('<root><Only id="1">x</Only></root>')
    expect(result).toMatch(/<Only id="1">/)
    expect(result).not.toMatch(/<Only\n/)
  })

  it('does not insert a space before a self-closing slash', () => {
    const single = formatXmlIndentAttributes('<root><Empty id="x"/></root>')
    expect(single).toMatch(/<Empty id="x"\/>/)
    expect(single).not.toMatch(/ \/>/)

    const several = formatXmlIndentAttributes('<root><Empty id="x" kind="a"/></root>')
    expect(several).toMatch(/<Empty id="x"\n {9}kind="a"\/>/)
    expect(several).not.toMatch(/ \/>/)
  })

  it('keeps > that sits inside an attribute value', () => {
    const result = formatXmlIndentAttributes('<root><tag note="a>b" id="1">x</tag></root>')
    expect(result).toMatch(/<tag note="a>b"\n {7}id="1">/)
  })

  it('does not rewrite tags inside comments or CDATA', () => {
    const commented = formatXmlIndentAttributes(
      '<root><!-- <tag a="1"> --><child b="2">t</child></root>',
    )
    expect(commented).toContain('<!-- <tag a="1"> -->')
    expect(commented).toMatch(/<child b="2">/)

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
