import { describe, it, expect } from 'vitest'
import { escapeXmlText, unescapeXmlText } from './escapeXml'

describe('escapeXmlText', () => {
  it('escapes all five XML special characters', () => {
    expect(escapeXmlText('&<>"\'')).toBe('&amp;&lt;&gt;&quot;&apos;')
  })

  it('escapes characters inside a fragment', () => {
    expect(escapeXmlText('<tag attr="x">a & b</tag>')).toBe(
      '&lt;tag attr=&quot;x&quot;&gt;a &amp; b&lt;/tag&gt;',
    )
  })
})

describe('unescapeXmlText', () => {
  it('unescapes all five XML special characters', () => {
    expect(unescapeXmlText('&amp;&lt;&gt;&quot;&apos;')).toBe('&<>"\'')
  })

  it('unescapes a fragment back to raw text', () => {
    expect(unescapeXmlText('&lt;tag attr=&quot;x&quot;&gt;a &amp; b&lt;/tag&gt;')).toBe(
      '<tag attr="x">a & b</tag>',
    )
  })

  it('round-trips with escapeXmlText', () => {
    const raw = '<tag attr="x">a & b\'</tag>'
    expect(unescapeXmlText(escapeXmlText(raw))).toBe(raw)
  })
})
