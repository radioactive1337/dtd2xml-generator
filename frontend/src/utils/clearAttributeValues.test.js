import { describe, it, expect } from 'vitest'
import { clearAttributeValues } from './clearAttributeValues'

describe('clearAttributeValues', () => {
  it('blanks a double-quoted attribute value', () => {
    expect(clearAttributeValues('<tag attr="value">')).toBe('<tag attr="">')
  })

  it('blanks a single-quoted attribute value', () => {
    expect(clearAttributeValues("<tag attr='value'>")).toBe("<tag attr=''>")
  })

  it('blanks multiple attributes on one element', () => {
    expect(clearAttributeValues('<tag a="1" b=\'2\' c="3">')).toBe(
      '<tag a="" b=\'\' c="">',
    )
  })

  it('blanks attributes across multiple elements', () => {
    const input = '<a x="1"><b y="2"/></a>'
    expect(clearAttributeValues(input)).toBe('<a x=""><b y=""/></a>')
  })

  it('preserves attribute name and spacing around =', () => {
    expect(clearAttributeValues('<tag attr = "value">')).toBe('<tag attr = "">')
  })

  it('preserves namespaced attribute names', () => {
    expect(clearAttributeValues('<tag xsi:type="Foo">')).toBe('<tag xsi:type="">')
  })

  it('handles values containing =, whitespace, and the other quote type', () => {
    expect(clearAttributeValues('<tag attr="a=b c \'d\'">')).toBe('<tag attr="">')
  })

  it('leaves text with no attributes unchanged', () => {
    const input = '<tag>plain text, no attrs here</tag>'
    expect(clearAttributeValues(input)).toBe(input)
  })

  it('leaves already-empty attribute values unchanged', () => {
    expect(clearAttributeValues('<tag attr="">')).toBe('<tag attr="">')
  })

  it('blanks whatever attribute value falls inside a partial/mid-tag selection', () => {
    // Selection can start mid-tag; the transform only sees the selected substring.
    expect(clearAttributeValues('attr="value" other="x">')).toBe('attr="" other="">')
  })
})
