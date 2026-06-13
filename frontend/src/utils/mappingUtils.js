import { normalizeTreePath } from './xmlPaths'

/** Normalize a field/column name for fuzzy matching. */
export function normalizeFieldName(name) {
  return (name || '').toLowerCase().replace(/^@/, '').replace(/[-_]/g, '')
}

/** Last dot-separated segment of a path (after group-N normalization). */
export function lastPathSegment(path) {
  const normalized = normalizeTreePath((path || '').trim())
  if (!normalized) return ''
  const parts = normalized.split('.')
  return parts[parts.length - 1] || ''
}

/** Filter dot-paths whose last segment equals the given tag. */
export function pathsEndingWithTag(paths, tag) {
  if (!tag || !paths?.length) return []
  return paths.filter((p) => lastPathSegment(p) === tag)
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
    errors.push('DB alias is required')
  }
  if (!mapping.query?.trim()) {
    errors.push('SQL query is required')
  }
  if (!mapping.target_element?.trim()) {
    errors.push('Target element is required')
  } else if (elements?.length && !elements.includes(mapping.target_element)) {
    errors.push(`Target element "${mapping.target_element}" is not in the DTD`)
  }

  const filledPairs = (mapping.fields || []).filter((f) => f.db_col && f.xml_attr)
  if (!filledPairs.length) {
    errors.push('At least one field mapping (DB column → XML attribute) is required')
  }

  const xmlAttrs = filledPairs.map((f) => f.xml_attr)
  const seen = new Set()
  for (const attr of xmlAttrs) {
    const key = normalizeFieldName(attr)
    if (seen.has(key)) {
      errors.push(`Duplicate XML attribute "${attr}"`)
      break
    }
    seen.add(key)
  }

  if (preview?.error) {
    errors.push(preview.error)
  } else if (preview && !preview.loading) {
    if (preview.columns?.length && preview.row === null) {
      warnings.push('Query returned 0 rows')
    }
  }

  return { errors, warnings }
}

/** Apply auto-suggest to empty xml_attr slots without overwriting filled pairs. */
export function applyAutoSuggestToFields(fields, columns, xmlAttributes) {
  const suggestions = suggestFieldMappings(columns, xmlAttributes, fields)
  return fields.map((field, i) => {
    if (field.xml_attr?.trim()) return field
    const suggested = suggestions[i]
    if (!suggested) return field
    return { ...field, xml_attr: suggested.xml_attr || field.xml_attr }
  })
}
