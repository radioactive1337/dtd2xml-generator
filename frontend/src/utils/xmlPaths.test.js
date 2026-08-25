import { describe, it, expect } from 'vitest'
import {
  canonicalizeXmlElementName,
  canonicalizeXmlElementPaths,
  normalizeElementPathsForTreeSync,
  peekXmlRootElement,
} from './xmlPaths'

describe('peekXmlRootElement', () => {
  it('returns the local name of the document element', () => {
    expect(peekXmlRootElement('<abt-accounts><bank/></abt-accounts>')).toBe('abt-accounts')
  })

  it('strips a namespace prefix', () => {
    expect(peekXmlRootElement('<ns:PayDoc xmlns:ns="urn:x"/>')).toBe('PayDoc')
  })

  it('skips XML declaration and comments', () => {
    const xml = `<?xml version="1.0"?>\n<!-- sample -->\n<abs-client id="1"/>`
    expect(peekXmlRootElement(xml)).toBe('abs-client')
  })

  it('returns empty string when there is no element', () => {
    expect(peekXmlRootElement('')).toBe('')
    expect(peekXmlRootElement('   ')).toBe('')
    expect(peekXmlRootElement('not xml')).toBe('')
  })
})

describe('normalizeElementPathsForTreeSync', () => {
  it('collapses sibling indices to one structural path', () => {
    const paths = [
      'PayDoc.Body.client.operation[0]',
      'PayDoc.Body.client.operation[99]',
      'PayDoc.Body.client.operation[0].amount',
    ]
    const result = normalizeElementPathsForTreeSync(paths)
    expect(result).toContain('PayDoc.Body.client.operation')
    expect(result).toContain('PayDoc.Body.client.operation.amount')
    expect(result.filter((p) => p.endsWith('operation')).length).toBe(1)
    expect(result.some((p) => p.includes('[0]'))).toBe(false)
  })

  it('strips group-N segments', () => {
    const result = normalizeElementPathsForTreeSync(['Root.group-0.Field'])
    expect(result).toEqual(['Root.Field'])
  })

  it('dedupes and sorts shallow to deep', () => {
    const result = normalizeElementPathsForTreeSync(['A.B.C', 'A', 'A.B'])
    expect(result).toEqual(['A', 'A.B', 'A.B.C'])
  })
})

describe('canonicalizeXmlElementPaths', () => {
  const elements = ['PayDoc', 'cs:update-object', 'cs:add-field']

  it('maps local XML names to qualified DTD names', () => {
    expect(canonicalizeXmlElementName('update-object', elements)).toBe('cs:update-object')
    expect(
      canonicalizeXmlElementPaths(
        ['update-object', 'update-object.add-field[0]'],
        elements,
      ),
    ).toEqual(['cs:update-object', 'cs:update-object.cs:add-field[0]'])
  })

  it('keeps unknown XML names unchanged', () => {
    expect(canonicalizeXmlElementName('unknown', elements)).toBe('unknown')
  })
})
