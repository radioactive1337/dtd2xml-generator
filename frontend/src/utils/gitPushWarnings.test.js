import { describe, it, expect } from 'vitest'
import {
  PUSH_WARNINGS_REQUIRE_ACK,
  extractPushWarnings,
  formatPushWarningLabel,
  parsePushFeedback,
  parsePushFeedbackItem,
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

describe('parsePushFeedback', () => {
  it('splits a rule-check error into a heading and list items', () => {
    const text = [
      'Документ не прошёл проверку правил атрибутов для отправки в Git:',
      '- PayDoc.attribute[0]@value: ИНН организации (CorpSender): 10 цифр',
      '- PayDoc.attribute[1]@value: Паспорт РФ: серия 4 цифры, номер 6 цифр, код подразделения XXX-XXX, дата YYYY-MM-DD',
      '… и ещё 3',
    ].join('\n')
    expect(parsePushFeedback(text)).toEqual({
      heading: 'Документ не прошёл проверку правил атрибутов для отправки в Git:',
      items: [
        {
          location: 'PayDoc.attribute[0]@value',
          message: 'ИНН организации (CorpSender): 10 цифр',
        },
        {
          location: 'PayDoc.attribute[1]@value',
          message:
            'Паспорт РФ: серия 4 цифры, номер 6 цифр, код подразделения XXX-XXX, дата YYYY-MM-DD',
        },
      ],
      more: '… и ещё 3',
    })
  })

  it('keeps a namespaced path together when splitting location and message', () => {
    expect(
      parsePushFeedbackItem(
        '{http://example.com/cs}attribute[0]@value: ИНН организации (CorpSender): 10 цифр',
      ),
    ).toEqual({
      location: '{http://example.com/cs}attribute[0]@value',
      message: 'ИНН организации (CorpSender): 10 цифр',
    })
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
