import client from './client'

export async function uploadDtd(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/dtd/upload', form)
  return data
}

export async function listElements(schemaId) {
  const { data } = await client.get(`/dtd/${schemaId}/elements`)
  return data
}

export async function getElementTree(schemaId, elementName) {
  const { data } = await client.get(`/dtd/${schemaId}/elements/${elementName}/tree`)
  return data
}

export async function getConfigAliases() {
  const { data } = await client.get('/config/aliases')
  return data
}
