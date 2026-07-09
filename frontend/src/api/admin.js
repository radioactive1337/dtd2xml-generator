import client from './client'

export async function fetchAdminStats() {
  const { data } = await client.get('/admin/stats')
  return data
}

export async function fetchAdminUsers() {
  const { data } = await client.get('/admin/users')
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
