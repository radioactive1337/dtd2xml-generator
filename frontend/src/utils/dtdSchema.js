export function schemaFileName(schema) {
  const source = schema.source_files?.[0] || ''
  return source.split(/[/\\]/).pop() || 'schema'
}

export function pickPrimarySchema(schemas) {
  if (!schemas.length) return null
  const main = schemas.find((s) =>
    s.source_files?.some((f) => /[/\\]main\.dtd$/i.test(f) || f.toLowerCase() === 'main.dtd'),
  )
  if (main) return main
  return schemas.reduce(
    (best, s) => (!best || s.element_count > best.element_count ? s : best),
    null,
  )
}
