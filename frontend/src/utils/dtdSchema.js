export function schemaFileName(schema) {
  const source = schema.source_files?.[0] || ''
  return source.split(/[/\\]/).pop() || 'schema'
}

export function dtdLocalName(name) {
  const colon = name.indexOf(':')
  return colon > 0 ? name.slice(colon + 1) : name
}

export function collectElementsFromSchemas(schemas) {
  const names = new Set()
  for (const schema of schemas) {
    for (const name of schema.elements || []) {
      names.add(name)
      names.add(dtdLocalName(name))
    }
  }
  return [...names].sort()
}

export function pickPrimarySchema(schemas) {
  if (!schemas.length) return null
  for (const preferred of ['main.dtd', 'v2.dtd']) {
    const match = schemas.find((s) =>
      s.source_files?.some((f) => {
        const name = f.split(/[/\\]/).pop()?.toLowerCase()
        return name === preferred
      }),
    )
    if (match) return match
  }
  return schemas.reduce(
    (best, s) => (!best || s.element_count > best.element_count ? s : best),
    null,
  )
}

export function normalizeDtdUploadResult(result) {
  if (!result?.schemas?.length) return result
  const primary =
    result.schemas.find((schema) => schema.schema_id === result.primary_schema_id) ||
    pickPrimarySchema(result.schemas)
  return {
    ...primary,
    schemas: result.schemas,
    primary_schema_id: result.primary_schema_id,
  }
}
