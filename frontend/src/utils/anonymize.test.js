import { describe, it, expect } from 'vitest'
import {
  buildRequestPayload,
  buildRule,
  downloadFileName,
  effectiveCategory,
  emptyRuleForm,
  fieldLabel,
  filterRules,
  formToRule,
  planBulkReplace,
  groupCategoriesByGroup,
  groupFindingsByCategory,
  isHandoffBlocked,
  overridesToPayload,
  reportStatus,
  ruleKey,
  ruleScopeOptions,
  ruleSummary,
  ruleToForm,
  safeErrorMessage,
} from './anonymize'

describe('safeErrorMessage', () => {
  it('never echoes request input', () => {
    expect(safeErrorMessage(new Error('[{"type":"x","input":"<secret/>"}]'))).toBe('Некорректные параметры запроса')
    expect(safeErrorMessage(new Error('boom'))).toBe('boom')
    expect(safeErrorMessage(new Error('x'.repeat(400))).length).toBe(301)
  })
})

describe('groupFindingsByCategory', () => {
  const findings = [
    { key: 'a|inn|', element: 'a', attr: 'inn', name: '', category: 'inn', category_label: 'ИНН', line: 3, masked_preview: '50****22' },
    { key: 'a|inn|', element: 'a', attr: 'inn', name: '', category: 'inn', category_label: 'ИНН', line: 9, masked_preview: '50****22' },
    { key: 'b|inn|', element: 'b', attr: 'inn', name: '', category: 'inn', category_label: 'ИНН', line: 12, masked_preview: '77****01' },
    { key: 'c|email|', element: 'c', attr: 'email', name: '', category: 'email', category_label: 'Email', line: 20, masked_preview: 'i***@x.ru' },
  ]

  it('groups by category sorted by count and merges fields', () => {
    const groups = groupFindingsByCategory(findings)
    expect(groups.map((g) => g.category)).toEqual(['inn', 'email'])
    expect(groups[0].count).toBe(3)
    expect(groups[0].fields).toHaveLength(2)
    expect(groups[0].fields[0]).toMatchObject({ key: 'a|inn|', count: 2, lines: [3, 9], previews: ['50****22'] })
  })

  it('handles empty input', () => {
    expect(groupFindingsByCategory(null)).toEqual([])
  })
})

describe('groupCategoriesByGroup', () => {
  it('keeps order and groups', () => {
    const groups = groupCategoriesByGroup([
      { id: 'a', group: 'Люди' },
      { id: 'b', group: 'Документы' },
      { id: 'c', group: 'Люди' },
      { id: 'd' },
    ])
    expect(groups.map((g) => g.name)).toEqual(['Люди', 'Документы', 'Прочее'])
    expect(groups[0].items.map((i) => i.id)).toEqual(['a', 'c'])
  })
})

describe('rules from queue items', () => {
  const pair = { element: 'cs:attribute', attr: 'value', name: 'Mystery' }
  const plain = { element: 'client', attr: 'taxId', name: '' }
  const text = { element: 'note', attr: '#text', name: '' }

  it('offers scopes depending on the item', () => {
    expect(ruleScopeOptions(pair).map((o) => o.id)).toEqual(['exact', 'attr', 'name'])
    expect(ruleScopeOptions(plain).map((o) => o.id)).toEqual(['exact', 'attr'])
    expect(ruleScopeOptions(text).map((o) => o.id)).toEqual(['exact'])
  })

  it('builds rules for each scope', () => {
    expect(buildRule(pair, 'exact', 'replace', 'inn')).toEqual({
      attr: 'value', action: 'replace', category: 'inn', source: 'manual', element: 'cs:attribute', name: 'Mystery',
    })
    expect(buildRule(pair, 'name', 'keep')).toEqual({
      attr: 'value', action: 'keep', category: null, source: 'manual', name: 'Mystery',
    })
    expect(buildRule(plain, 'attr', 'replace', 'phone')).toEqual({
      attr: 'taxId', action: 'replace', category: 'phone', source: 'manual',
    })
  })
})

describe('queue decisions', () => {
  const withHint = { key: 'bank|bic|', suggested_category: 'bic', ai_category: null }
  const plain = { key: 'note|text|', suggested_category: '', ai_category: null }

  it('uses a suggestion when the category select was not touched', () => {
    expect(effectiveCategory(withHint, undefined)).toBe('bic')
    expect(effectiveCategory(withHint, 'phone')).toBe('phone')
    expect(effectiveCategory(withHint, '')).toBe('')
    expect(effectiveCategory({ ai_category: 'email', suggested_category: 'phone' }, undefined)).toBe('email')
    expect(effectiveCategory({ ai_category: 'none', suggested_category: 'bic' }, undefined)).toBe('bic')
    expect(effectiveCategory(plain, undefined)).toBe('')
  })

  it('applies one category to the selection, or each field suggestion', () => {
    const items = [withHint, plain]
    expect(planBulkReplace(items, {}).ready.map((row) => row.key)).toEqual(['bank|bic|'])
    expect(planBulkReplace(items, {}).skipped).toEqual(['note|text|'])
    expect(planBulkReplace(items, { commonCategory: 'phone' }).ready).toEqual([
      { key: 'bank|bic|', category: 'phone' },
      { key: 'note|text|', category: 'phone' },
    ])
    expect(planBulkReplace(items, { picked: { 'bank|bic|': 'city' } }).ready).toEqual([
      { key: 'bank|bic|', category: 'city' },
    ])
  })
})

describe('rule form', () => {
  it('builds a personal rule and the same key the server uses', () => {
    const rule = formToRule({
      attr: ' value ',
      element: ' cs:attribute ',
      name: 'LastName',
      parent_element: '',
      parent_name: ' Passport ',
      parent_value: '',
      action: 'replace',
      category: 'person_last',
      note: '  ',
    })
    expect(rule).toEqual({
      attr: 'value',
      element: 'cs:attribute',
      name: 'LastName',
      parent_name: 'Passport',
      action: 'replace',
      category: 'person_last',
      source: 'manual',
    })
    expect(ruleKey(rule)).toBe('cs:attribute|value|lastname||passport|')
  })

  it('drops the category when the action is keep', () => {
    expect(formToRule({ attr: 'status', action: 'keep', category: 'inn' }).category).toBeNull()
  })

  it('round-trips a stored rule into an empty form', () => {
    const form = ruleToForm({ attr: 'inn', action: 'keep', element: 'client', note: 'код' })
    expect(form).toMatchObject({ attr: 'inn', action: 'keep', element: 'client', note: 'код', category: '' })
    expect(emptyRuleForm().action).toBe('replace')
  })
})

describe('payload', () => {
  it('serializes overrides and drops category for keep/skip', () => {
    expect(
      overridesToPayload({
        'a|b|': { action: 'replace', category: 'inn' },
        'c|d|': { action: 'keep', category: 'inn' },
      }),
    ).toEqual([
      { key: 'a|b|', action: 'replace', category: 'inn' },
      { key: 'c|d|', action: 'keep', category: null },
    ])
  })

  it('sends categories only when not all are enabled', () => {
    const base = { xmlText: '<a/>', overrides: {}, allCategoryIds: ['a', 'b'], schemaId: 'main' }
    expect(buildRequestPayload({ ...base, enabledCategories: ['a', 'b'] }).categories).toBeUndefined()
    expect(buildRequestPayload({ ...base, enabledCategories: ['a'] }).categories).toEqual(['a'])
    const payload = buildRequestPayload({ ...base, enabledCategories: ['a', 'b'], stripComments: false })
    expect(payload).toMatchObject({ schema_id: 'main', strip_comments: false })
  })
})

describe('strict mode', () => {
  it('blocks until suspicious fields are resolved or forced', () => {
    expect(isHandoffBlocked(null, false)).toBe(true)
    expect(isHandoffBlocked({ unresolved_suspicious: 2 }, false)).toBe(true)
    expect(isHandoffBlocked({ unresolved_suspicious: 2 }, true)).toBe(false)
    expect(isHandoffBlocked({ unresolved_suspicious: 0 }, false)).toBe(false)
  })

  it('reports status, treating leaks as review-worthy', () => {
    expect(reportStatus(null).id).toBe('none')
    expect(reportStatus({ unresolved_suspicious: 0, leak_check: { items: [] } }).id).toBe('clean')
    expect(reportStatus({ unresolved_suspicious: 1 }).id).toBe('needs_review')
    expect(reportStatus({ unresolved_suspicious: 0, leak_check: { items: [{}] } }).id).toBe('needs_review')
  })
})

describe('labels', () => {
  it('formats field labels', () => {
    expect(fieldLabel({ element: 'a', attr: 'b', name: '' })).toBe('a@b')
    expect(fieldLabel({ element: 'cs:attribute', attr: 'value', name: 'Inn' })).toBe('cs:attribute@value [Inn]')
    expect(fieldLabel({ element: 'note', attr: '#text', name: '' })).toBe('note@текст')
  })

  it('names the download', () => {
    expect(downloadFileName('Doc', 'real.xml')).toBe('real.anonymized.xml')
    expect(downloadFileName('Doc')).toBe('Doc.anonymized.xml')
    expect(downloadFileName('')).toBe('document.anonymized.xml')
  })

  it('summarises and filters rules', () => {
    const rules = [
      { id: '1', attr: 'inn', action: 'replace', category: 'inn', source: 'builtin' },
      { id: '2', element: 'cs:attribute', attr: 'value', name: 'Mystery', action: 'keep', source: 'manual', note: 'тест' },
    ]
    expect(ruleSummary(rules[1])).toBe('cs:attribute @value [name=Mystery]')
    expect(filterRules(rules, { query: 'mystery' }).map((r) => r.id)).toEqual(['2'])
    expect(filterRules(rules, { source: 'builtin' }).map((r) => r.id)).toEqual(['1'])
    expect(filterRules(rules, {})).toHaveLength(2)
  })
})
