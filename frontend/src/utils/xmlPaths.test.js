import { describe, it, expect } from 'vitest'
import { normalizeElementPathsForTreeSync } from './xmlPaths'

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
