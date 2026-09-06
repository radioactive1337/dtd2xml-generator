import { describe, it, expect } from 'vitest'
import { clearAttributeValues, openTagPrefix } from './clearAttributeValues'

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

  it('keeps name on cs:* tags and blanks value', () => {
    expect(
      clearAttributeValues('<cs:attribute name="LastName" value="Адаблин" />'),
    ).toBe('<cs:attribute name="LastName" value="" />')
  })

  it('keeps nested cs:attribute name keys', () => {
    const input =
      '<cs:attribute name="Passport">' +
      '<cs:attribute name="CardType" value="Паспорт РФ" />' +
      '</cs:attribute>'
    expect(clearAttributeValues(input)).toBe(
      '<cs:attribute name="Passport">' +
        '<cs:attribute name="CardType" value="" />' +
        '</cs:attribute>',
    )
  })

  it('still blanks name on non-cs tags', () => {
    expect(clearAttributeValues('<Field name="amount" type="number">')).toBe(
      '<Field name="" type="">',
    )
  })

  it('blanks cs: name when keepCsName is false', () => {
    expect(
      clearAttributeValues('<cs:attribute name="LastName" value="x" />', {
        keepCsName: false,
      }),
    ).toBe('<cs:attribute name="" value="" />')
  })

  it('keeps xmlns declarations', () => {
    expect(
      clearAttributeValues(
        '<cs:update-object xmlns:cs="http://www.faktura.ru/cs" document_type="d">',
      ),
    ).toBe(
      '<cs:update-object xmlns:cs="http://www.faktura.ru/cs" document_type="">',
    )
  })

  it('uses prefix lookbehind so a mid-tag selection still keeps cs: name', () => {
    expect(
      clearAttributeValues('name="LastName" value="Адаблин" />', {
        prefix: '<cs:attribute ',
      }),
    ).toBe('name="LastName" value="" />')
  })

  it('clears a typical cs:update-object payload except name keys', () => {
    const input = `
<cs:update-object xmlns:cs="http://www.faktura.ru/cs" document_type="d" source="interpay">
  <cs:object type="person">
    <cs:attribute name="LastName" value="Адаблин" />
    <cs:attribute name="Address" value="Legal">
      <cs:attribute name="Index" value="094025" />
    </cs:attribute>
  </cs:object>
</cs:update-object>`
    const result = clearAttributeValues(input)
    expect(result).toContain('xmlns:cs="http://www.faktura.ru/cs"')
    expect(result).toContain('name="LastName"')
    expect(result).toContain('name="Address"')
    expect(result).toContain('name="Index"')
    expect(result).toContain('document_type=""')
    expect(result).toContain('source=""')
    expect(result).toContain('type=""')
    expect(result).toContain('value=""')
    expect(result).not.toContain('value="Адаблин"')
    expect(result).not.toContain('value="Legal"')
  })
})

describe('openTagPrefix', () => {
  it('returns the open tag when the cursor is inside it', () => {
    expect(openTagPrefix('<cs:attribute ')).toBe('<cs:attribute ')
    expect(openTagPrefix('foo\n<cs:attribute name=')).toBe('<cs:attribute name=')
  })

  it('returns empty when the cursor is outside a tag', () => {
    expect(openTagPrefix('<cs:attribute name="x">')).toBe('')
    expect(openTagPrefix('')).toBe('')
  })
})
