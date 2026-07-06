import { describe, expect, it } from 'vitest'
import { dtdDocPlainText, dtdDocPreview, sanitizeDtdDocHtml } from './dtdDoc'

describe('dtdDoc', () => {
  it('returns plain text unchanged', () => {
    expect(dtdDocPlainText('Описание банка')).toBe('Описание банка')
  })

  it('strips html to plain text via fallback', () => {
    const raw = 'bank <ul><li>БИК: bic-type=ru</li><li>SWIFT</li></ul>'
    expect(dtdDocPlainText(raw)).toContain('БИК')
    expect(dtdDocPlainText(raw)).not.toContain('<ul>')
  })

  it('sanitizes allowed html tags via fallback', () => {
    const html = sanitizeDtdDocHtml('<ul><li>one</li><li>two</li></ul>')
    expect(html).toContain('one')
    expect(html).toContain('two')
    expect(html).not.toContain('<script')
  })

  it('escapes plain multiline text', () => {
    const html = sanitizeDtdDocHtml('line one\nline two')
    expect(html).toContain('line one')
    expect(html).toContain('<br>')
  })

  it('truncates preview', () => {
    const long = 'a'.repeat(200)
    expect(dtdDocPreview(long, 50).length).toBeLessThanOrEqual(50)
  })
})
