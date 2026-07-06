import { describe, expect, it } from 'vitest'
import { filterElements, resolveElementName } from './elementFilter'

const elements = ['Footer', 'MakePayment', 'PayDoc', 'Payment', 'PaymentInfo', 'Title']

describe('filterElements', () => {
  it('puts exact match first, then prefix, then substring', () => {
    const { matches } = filterElements(elements, 'payment')
    expect(matches[0]).toBe('Payment')
    expect(matches).toEqual(['Payment', 'PaymentInfo', 'MakePayment'])
  })

  it('keeps alphabetical order within the same match tier', () => {
    const { matches } = filterElements(elements, 'pay')
    expect(matches).toEqual(['PayDoc', 'Payment', 'PaymentInfo', 'MakePayment'])
  })

  it('returns default slice when query is too short', () => {
    const { matches, total } = filterElements(elements, 'p')
    expect(matches).toEqual(elements.slice(0, 50))
    expect(total).toBe(elements.length)
  })
})

describe('resolveElementName', () => {
  it('resolves normalized exact match', () => {
    expect(resolveElementName('payment', elements)).toBe('Payment')
  })
})
