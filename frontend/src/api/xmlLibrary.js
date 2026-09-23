import client from './client'

export async function getSharedStatus() {
  const { data } = await client.get('/xml-library/shared/status')
  return data
}

export async function syncSharedLibrary() {
  const { data } = await client.post('/xml-library/shared/sync')
  return data
}

export async function listSharedCategories() {
  const { data } = await client.get('/xml-library/shared/categories')
  return data
}

export async function listSharedDocuments(category) {
  const { data } = await client.get(
    `/xml-library/shared/categories/${encodeURIComponent(category)}`,
  )
  return data
}

export async function loadSharedDocument(category, docId) {
  const { data } = await client.get(
    `/xml-library/shared/categories/${encodeURIComponent(category)}/${encodeURIComponent(docId)}`,
  )
  return data
}

export async function listPersonalDocuments() {
  const { data } = await client.get('/xml-library/personal')
  return data
}

export async function listPersonalFolders() {
  const { data } = await client.get('/xml-library/personal/folders')
  return data.folders || []
}

export async function createPersonalFolder(name) {
  const { data } = await client.post('/xml-library/personal/folders', { name })
  return data.folders || []
}

export async function renamePersonalFolder(name, nextName) {
  const { data } = await client.patch(
    `/xml-library/personal/folders/${encodeURIComponent(name)}`,
    { name: nextName },
  )
  return data.folders || []
}

export async function deletePersonalFolder(name) {
  const { data } = await client.delete(
    `/xml-library/personal/folders/${encodeURIComponent(name)}`,
  )
  return data.folders || []
}

export async function movePersonalDocument(name, folder) {
  const { data } = await client.patch(
    `/xml-library/personal/${encodeURIComponent(name)}/folder`,
    { folder },
  )
  return data
}

export async function savePersonalDocument(document) {
  const { data } = await client.post('/xml-library/personal', document)
  return data
}

export async function loadPersonalDocument(name) {
  const { data } = await client.get(
    `/xml-library/personal/${encodeURIComponent(name)}`,
  )
  return data
}

export async function updatePersonalDocument(name, document) {
  const { data } = await client.put(
    `/xml-library/personal/${encodeURIComponent(name)}`,
    document,
  )
  return data
}

export async function deletePersonalDocument(name) {
  const { data } = await client.delete(
    `/xml-library/personal/${encodeURIComponent(name)}`,
  )
  return data
}

export async function pushDocumentToGit(payload) {
  const { data } = await client.post('/xml-library/shared/push', {
    ...payload,
    acknowledge_warnings: Boolean(payload.acknowledge_warnings),
  })
  return data
}

export async function shareDocument(payload) {
  const { data } = await client.post('/xml-library/share', payload)
  return data
}
