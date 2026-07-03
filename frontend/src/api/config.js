import client from './client'

export async function getConfigAliases() {
  const { data } = await client.get('/config/aliases')
  return data
}

export async function getConnections() {
  const { data } = await client.get('/config/connections')
  return data
}

export async function testDbConnection(alias) {
  const { data } = await client.post('/config/test-db', { alias })
  return data
}

export async function testLlmConnection(alias) {
  const { data } = await client.post('/config/test-llm', { alias })
  return data
}

export async function setDefaultLlmAlias(alias) {
  const { data } = await client.put('/config/default-llm', { alias })
  return data
}

export async function createDatabaseAlias(payload) {
  const { data } = await client.post('/config/databases', payload)
  return data
}

export async function updateDatabaseAlias(alias, payload) {
  const { data } = await client.put(`/config/databases/${encodeURIComponent(alias)}`, payload)
  return data
}

export async function deleteDatabaseAlias(alias) {
  const { data } = await client.delete(`/config/databases/${encodeURIComponent(alias)}`)
  return data
}

export async function createLlmAlias(payload) {
  const { data } = await client.post('/config/llm', payload)
  return data
}

export async function updateLlmAlias(alias, payload) {
  const { data } = await client.put(`/config/llm/${encodeURIComponent(alias)}`, payload)
  return data
}

export async function deleteLlmAlias(alias) {
  const { data } = await client.delete(`/config/llm/${encodeURIComponent(alias)}`)
  return data
}
