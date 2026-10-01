/** Pure helpers for the anonymization page (no network, no storage). */

export const TEXT_ATTR = '#text'
export const MAX_XML_CHARS = 8_000_000

/**
 * Error text that is safe to show: validation errors from the server may echo
 * the request input (i.e. the real XML), so never display those verbatim.
 */
export function safeErrorMessage(err) {
  const text = String(err?.message || err || '')
  if (/"input"\s*:|"ctx"\s*:/.test(text)) return 'Некорректные параметры запроса'
  return text.length > 300 ? `${text.slice(0, 300)}…` : text
}

export const CONSISTENCY_MODES = [
  {
    id: 'document',
    label: 'В пределах документа',
    hint: 'Одно и то же значение заменяется одинаково внутри документа. При каждом запуске замены другие.',
  },
  {
    id: 'user',
    label: 'Стабильно для меня',
    hint: 'Тот же исходный человек всегда превращается в того же вымышленного — между запусками и документами.',
  },
  {
    id: 'project',
    label: 'Общий seed проекта',
    hint: 'Одинаковый результат у всех, кто использует один seed (удобно для связанных документов команды).',
  },
]

/** `Element@attr` or `Element@attr[name]` — human readable field label. */
export function fieldLabel(item) {
  const attr = item.attr === TEXT_ATTR ? 'текст' : item.attr
  const base = item.element ? `${item.element}@${attr}` : attr
  return item.name ? `${base} [${item.name}]` : base
}

export function groupFindingsByCategory(findings) {
  const groups = new Map()
  for (const f of findings || []) {
    const id = f.category || 'unknown'
    let group = groups.get(id)
    if (!group) {
      group = { category: id, label: f.category_label || id, count: 0, fields: new Map() }
      groups.set(id, group)
    }
    group.count += 1
    let field = group.fields.get(f.key)
    if (!field) {
      field = {
        key: f.key,
        element: f.element,
        attr: f.attr,
        name: f.name,
        source: f.source,
        action: f.action,
        count: 0,
        lines: [],
        previews: [],
      }
      group.fields.set(f.key, field)
    }
    field.count += 1
    if (f.line != null && field.lines.length < 5) field.lines.push(f.line)
    if (f.masked_preview && field.previews.length < 2 && !field.previews.includes(f.masked_preview)) {
      field.previews.push(f.masked_preview)
    }
  }
  return [...groups.values()]
    .map((g) => ({ ...g, fields: [...g.fields.values()].sort((a, b) => b.count - a.count) }))
    .sort((a, b) => b.count - a.count)
}

export function groupCategoriesByGroup(categories) {
  const groups = new Map()
  for (const c of categories || []) {
    const name = c.group || 'Прочее'
    if (!groups.has(name)) groups.set(name, [])
    groups.get(name).push(c)
  }
  return [...groups.entries()].map(([name, items]) => ({ name, items }))
}

/** Scopes in which a decision about a queue item can be remembered as a rule. */
export function ruleScopeOptions(item) {
  const options = [
    {
      id: 'exact',
      label: item.name
        ? `Это поле (${item.element}, ${item.attr}, name=${item.name})`
        : `Это поле (${item.element || 'любой элемент'}, ${item.attr === TEXT_ATTR ? 'текст' : item.attr})`,
    },
  ]
  if (item.attr !== TEXT_ATTR && item.element) {
    options.push({ id: 'attr', label: `Любой элемент с атрибутом «${item.attr}»` })
  }
  if (item.name) {
    options.push({
      id: 'name',
      label: `Любой элемент с name=«${item.name}» (cs:*)`,
    })
  }
  return options
}

export function buildRule(item, scope, action, category) {
  const rule = {
    attr: item.attr,
    action,
    category: action === 'replace' ? category : null,
    source: 'manual',
  }
  if (scope === 'exact') {
    if (item.element) rule.element = item.element
    if (item.name) rule.name = item.name
  } else if (scope === 'name') {
    if (item.name) rule.name = item.name
  }
  // scope === 'attr': attribute only, any element.
  return rule
}

/** Overrides map -> API list. */
export function overridesToPayload(overrides) {
  return Object.entries(overrides || {}).map(([key, value]) => ({
    key,
    action: value.action,
    category: value.action === 'replace' ? value.category : null,
  }))
}

export function buildRequestPayload(state) {
  const payload = {
    xml_text: state.xmlText,
    strip_comments: state.stripComments !== false,
    overrides: overridesToPayload(state.overrides),
  }
  if (state.schemaId) payload.schema_id = state.schemaId
  const all = state.allCategoryIds || []
  const enabled = state.enabledCategories || []
  if (all.length && enabled.length !== all.length) payload.categories = [...enabled]
  return payload
}

/**
 * Strict mode: while suspicious unclassified fields remain, the result must
 * not be handed out unless the user explicitly overrides the block.
 */
export function isHandoffBlocked(report, force) {
  if (!report) return true
  if (force) return false
  return (report.unresolved_suspicious || 0) > 0
}

export function leakCount(report) {
  return report?.leak_check?.items?.length || 0
}

export function reportStatus(report) {
  if (!report) return { id: 'none', label: '', tone: 'muted' }
  const blocking = (report.unresolved_suspicious || 0) > 0 || leakCount(report) > 0
  if (blocking) {
    return { id: 'needs_review', label: 'Требует проверки', tone: 'warning' }
  }
  return { id: 'clean', label: 'Замена выполнена', tone: 'success' }
}

export function downloadFileName(rootElement, original = '') {
  const base = (original || '').replace(/\.xml$/i, '')
  if (base) return `${base}.anonymized.xml`
  return `${rootElement || 'document'}.anonymized.xml`
}

export function filterRules(rules, { query = '', source = '' } = {}) {
  const q = query.trim().toLowerCase()
  return (rules || []).filter((r) => {
    if (source && r.source !== source) return false
    if (!q) return true
    const haystack = [r.element, r.attr, r.name, r.category, r.note, r.parent_element, r.parent_name]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(q)
  })
}

export function ruleSummary(rule) {
  const parts = []
  if (rule.element) parts.push(rule.element)
  parts.push(`@${rule.attr === TEXT_ATTR ? 'текст' : rule.attr}`)
  if (rule.name) parts.push(`[name=${rule.name}]`)
  if (rule.parent_name || rule.parent_element || rule.parent_value) {
    const p = [rule.parent_element, rule.parent_name && `name=${rule.parent_name}`, rule.parent_value && `value=${rule.parent_value}`]
      .filter(Boolean)
      .join(', ')
    parts.push(`← ${p}`)
  }
  return parts.join(' ')
}
