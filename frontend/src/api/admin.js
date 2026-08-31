import client from './client'

export async function fetchAdminStats() {
  const { data } = await client.get('/admin/stats')
  return data
}

export async function fetchAdminUsers() {
  const { data } = await client.get('/admin/users')
  return data
}

export async function createAdminUser(username) {
  const { data } = await client.post('/admin/users', { username })
  return data
}

export async function deleteAdminUser(userId) {
  const { data } = await client.delete(`/admin/users/${userId}`)
  return data
}

export async function downloadBackup() {
  const response = await client.get('/admin/backup', { responseType: 'blob' })
  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const filename = match?.[1] || 'xml-generator-backup.zip'

  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export async function fetchAdminSettings() {
  const { data } = await client.get('/admin/settings')
  return data
}

export async function updateAdminSettings(settings) {
  const { data } = await client.put('/admin/settings', settings)
  return data
}

export async function fetchAdminConnections() {
  const { data } = await client.get('/admin/connections')
  return data
}

export async function createAdminDatabaseAlias(payload) {
  const { data } = await client.post('/admin/databases', payload)
  return data
}

export async function updateAdminDatabaseAlias(alias, payload) {
  const { data } = await client.put(`/admin/databases/${encodeURIComponent(alias)}`, payload)
  return data
}

export async function deleteAdminDatabaseAlias(alias) {
  const { data } = await client.delete(`/admin/databases/${encodeURIComponent(alias)}`)
  return data
}

export async function createAdminLlmAlias(payload) {
  const { data } = await client.post('/admin/llm', payload)
  return data
}

export async function updateAdminLlmAlias(alias, payload) {
  const { data } = await client.put(`/admin/llm/${encodeURIComponent(alias)}`, payload)
  return data
}

export async function deleteAdminLlmAlias(alias) {
  const { data } = await client.delete(`/admin/llm/${encodeURIComponent(alias)}`)
  return data
}

export async function testAdminDbConnection(alias) {
  const { data } = await client.post('/admin/test-db', { alias })
  return data
}

export async function testAdminLlmConnection(alias) {
  const { data } = await client.post('/admin/test-llm', { alias })
  return data
}
