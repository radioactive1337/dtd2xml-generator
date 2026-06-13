import client from './client'

export async function getConfigAliases() {
  const { data } = await client.get('/config/aliases')
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
