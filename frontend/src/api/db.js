import client from './client'

export async function fetchQueryColumns(dbAlias, query) {
  const { data } = await client.post('/db/query-columns', {
    db_alias: dbAlias,
    query,
  })
  return data
}

export async function fetchQueryPreview(dbAlias, query) {
  const { data } = await client.post('/db/query-preview', {
    db_alias: dbAlias,
    query,
  })
  return data
}
