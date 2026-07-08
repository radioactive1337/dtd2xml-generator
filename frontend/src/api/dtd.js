import client from './client'

export async function uploadDtd(files) {
  const list = Array.isArray(files) ? files : [files]
  const form = new FormData()
  for (const file of list) {
    form.append('files', file)
  }
  const { data } = await client.post('/dtd/upload', form)
  return data
}

export async function uploadDtdJar(file) {
  const form = new FormData()
  form.append('file', file)
  form.append('inner_path', 'META-INF/dtd/')
  const { data } = await client.post('/dtd/upload-jar', form)
  return data
}

export async function listSchemas() {
  const { data } = await client.get('/dtd/schemas')
  return data
}

export async function getNexusConfig() {
  const { data } = await client.get('/dtd/nexus-config')
  return data
}

export async function pullDtdFromNexus() {
  const { data } = await client.post('/dtd/pull-nexus')
  return data
}

export async function listElements(schemaId) {
  const { data } = await client.get(`/dtd/${schemaId}/elements`)
  return data
}

const elementTreeCache = new Map()

function cacheKey(schemaId, elementName) {
  return `${schemaId}:${elementName}`
}

/** Drop cached element trees for one schema or the entire session. */
export function clearElementTreeCache(schemaId = null) {
  if (!schemaId) {
    elementTreeCache.clear()
    return
  }
  const prefix = `${schemaId}:`
  for (const key of elementTreeCache.keys()) {
    if (key.startsWith(prefix)) elementTreeCache.delete(key)
  }
}

export async function getElementTree(schemaId, elementName) {
  const key = cacheKey(schemaId, elementName)
  if (elementTreeCache.has(key)) {
    return elementTreeCache.get(key)
  }
  const { data } = await client.get(`/dtd/${schemaId}/elements/${elementName}/tree`)
  elementTreeCache.set(key, data)
  return data
}
