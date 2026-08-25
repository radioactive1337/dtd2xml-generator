import { describe, it, expect } from 'vitest'
import {
  PUSH_WARNINGS_REQUIRE_ACK,
  extractPushWarnings,
  formatPushWarningLabel,
} from './gitPushWarnings'

describe('extractPushWarnings', () => {
  it('returns structured warnings from a 409 acknowledgement payload', () => {
    const err = {
      response: {
        data: {
          detail: {
            code: PUSH_WARNINGS_REQUIRE_ACK,
            message: 'Подтвердите отправку',
            warnings: [{ location: 'PayDoc@status', message: 'неверный status' }],
            warning_count: 1,
          },
        },
      },
    }
    expect(extractPushWarnings(err)).toEqual({
      warnings: [{ location: 'PayDoc@status', message: 'неверный status' }],
      warningCount: 1,
      message: 'Подтвердите отправку',
    })
  })

  it('returns null for ordinary API errors', () => {
    expect(extractPushWarnings(new Error('fail'))).toBeNull()
    expect(
      extractPushWarnings({ response: { data: { detail: 'Документ не прошёл проверку' } } }),
    ).toBeNull()
  })
})

describe('formatPushWarningLabel', () => {
  it('joins location and message', () => {
    expect(
      formatPushWarningLabel({ location: 'PayDoc@status', message: 'неверный status' }),
    ).toBe('PayDoc@status — неверный status')
  })

  it('falls back to path@attr when location is missing', () => {
    expect(
      formatPushWarningLabel({ path: 'PayDoc', attr: 'status', message: 'неверный status' }),
    ).toBe('PayDoc@status — неверный status')
  })
})
