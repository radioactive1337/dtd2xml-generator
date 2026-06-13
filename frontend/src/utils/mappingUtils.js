import { normalizeTreePath, stripPathIndex } from './xmlPaths'

/** Normalize a field/column name for fuzzy matching. */
export function normalizeFieldName(name) {
  return (name || '').toLowerCase().replace(/^@/, '').replace(/[-_]/g, '')
}

/** Last dot-separated segment of a path (after group-N normalization). */
export function lastPathSegment(path) {
  const normalized = normalizeTreePath((path || '').trim())
  if (!normalized) return ''
  const parts = normalized.split('.')
  const last = parts[parts.length - 1] || ''
  return stripPathIndex(last)
}

/** Filter dot-paths whose last segment equals the given tag (case-insensitive). */
export function pathsEndingWithTag(paths, tag) {
  if (!tag || !paths?.length) return []
  const normTag = tag.trim().toLowerCase()
  return paths.filter((p) => lastPathSegment(p).toLowerCase() === normTag)
}

/**
 * Suggest db_col → xml_attr pairs from column and attribute names.
 * Exact normalized match first, then partial (contains). Skips already-used attrs.
 */
export function suggestFieldMappings(columns, xmlAttributes, existingPairs = []) {
  const usedAttrs = new Set(
    existingPairs
      .map((p) => normalizeFieldName(p.xml_attr))
      .filter(Boolean),
  )
  const available = (xmlAttributes || []).filter(
    (attr) => !usedAttrs.has(normalizeFieldName(attr)),
  )
  const suggestions = []

  for (const col of columns || []) {
    const normCol = normalizeFieldName(col)
    if (!normCol) {
      suggestions.push({ db_col: col, xml_attr: '' })
      continue
    }

    let match = available.find((attr) => normalizeFieldName(attr) === normCol)
    if (!match) {
      match = available.find((attr) => {
        const normAttr = normalizeFieldName(attr)
        return normCol.includes(normAttr) || normAttr.includes(normCol)
      })
    }

    if (match) {
      suggestions.push({ db_col: col, xml_attr: match })
      usedAttrs.add(normalizeFieldName(match))
      const idx = available.indexOf(match)
      if (idx >= 0) available.splice(idx, 1)
    } else {
      suggestions.push({ db_col: col, xml_attr: '' })
    }
  }

  return suggestions
}

/** Collect normalized element paths from a DTD content-model tree. */
export function collectDtdElementPaths(rootTag, contentModel, prefix = '') {
  const paths = []
  if (!contentModel) return paths

  const elementPath = prefix ? `${prefix}.${rootTag}` : rootTag
  paths.push(normalizeTreePath(elementPath))

  if (contentModel.kind === 'REF') {
    return paths
  }

  if (contentModel.kind === 'SEQUENCE' || contentModel.kind === 'CHOICE') {
    for (const [idx, child] of (contentModel.children || []).entries()) {
      if (child.kind === 'REF') {
        const childPath = `${elementPath}.${child.ref}`
        paths.push(normalizeTreePath(childPath))
        paths.push(...collectDtdElementPaths(child.ref, child, elementPath))
      } else if (child.kind === 'SEQUENCE' || child.kind === 'CHOICE') {
        paths.push(
          ...collectDtdElementPaths(`group-${idx}`, child, elementPath),
        )
      }
    }
  }

  return [...new Set(paths)]
}

/**
 * Validate a single mapping card. Returns { errors, warnings } string arrays.
 */
export function getMappingValidationIssues(mapping, { elements, preview }) {
  const errors = []
  const warnings = []

  if (!mapping.db_alias?.trim()) {
    errors.push('Укажите алиас БД')
  }
  if (!mapping.query?.trim()) {
    errors.push('Укажите SQL-запрос')
  }
  if (!mapping.target_element?.trim()) {
    errors.push('Укажите целевой элемент')
  } else if (elements?.length && !elements.includes(mapping.target_element)) {
    errors.push(`Элемент «${mapping.target_element}» не найден в DTD`)
  }

  const filledPairs = (mapping.fields || []).filter((f) => f.db_col && f.xml_attr)
  if (!filledPairs.length) {
    errors.push('Нужно хотя бы одно сопоставление поле БД → атрибут XML')
  }

  const xmlAttrs = filledPairs.map((f) => f.xml_attr)
  const seen = new Set()
  for (const attr of xmlAttrs) {
    const key = normalizeFieldName(attr)
    if (seen.has(key)) {
      errors.push(`Дублируется атрибут XML «${attr}»`)
      break
    }
    seen.add(key)
  }

  if (preview?.error) {
    errors.push(preview.error)
  } else if (preview && !preview.loading) {
    if (preview.columns?.length && preview.row === null) {
      warnings.push('Запрос не вернул строк')
    }
  }

  return { errors, warnings }
}

/**
 * Build one row per SQL column. Keeps manually filled pairs; suggests attrs for the rest.
 */
export function buildFieldMappingsFromColumns(columns, xmlAttributes, existingPairs = []) {
  const kept = (existingPairs || []).filter((f) => f.db_col?.trim() && f.xml_attr?.trim())
  const usedColNames = new Set(kept.map((f) => normalizeFieldName(f.db_col)))
  const colsToMap = (columns || []).filter((c) => !usedColNames.has(normalizeFieldName(c)))
  const suggestions = suggestFieldMappings(colsToMap, xmlAttributes, kept)
  const merged = [...kept, ...suggestions]
  return merged.length ? merged : [{ db_col: '', xml_attr: '' }]
}

/** After Test query: fill empty xml_attr and add rows for columns not yet listed. */
export function applyAutoSuggestToFields(fields, columns, xmlAttributes) {
  const result = (fields || []).map((f) => ({ ...f }))

  for (const field of result) {
    if (field.xml_attr?.trim() || !field.db_col?.trim()) continue
    const suggested = suggestFieldMappings([field.db_col], xmlAttributes, result)[0]
    if (suggested?.xml_attr) field.xml_attr = suggested.xml_attr
  }

  const usedCols = new Set(result.map((f) => normalizeFieldName(f.db_col)).filter(Boolean))
  const newCols = (columns || []).filter((c) => !usedCols.has(normalizeFieldName(c)))
  const newRows = suggestFieldMappings(newCols, xmlAttributes, result)
  const merged = [...result, ...newRows]
  return merged.length ? merged : [{ db_col: '', xml_attr: '' }]
}

/** Convert API mapping rows to editable field rows. */
export function mappingsToFields(mappings) {
  if (!mappings?.length) return [{ db_col: '', xml_attr: '' }]
  return mappings.map((m) => ({
    db_col: m.db_col || '',
    xml_attr: m.xml_attr || '',
  }))
}
