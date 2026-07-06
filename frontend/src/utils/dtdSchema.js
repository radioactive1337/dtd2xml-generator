export function schemaFileName(schema) {
  const source = schema.source_files?.[0] || ''
  return source.split(/[/\\]/).pop() || 'schema'
}

export function collectElementsFromSchemas(schemas) {
  return [...new Set(schemas.flatMap((schema) => schema.elements || []))].sort()
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
