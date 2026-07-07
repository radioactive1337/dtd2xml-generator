import client from './client'

export async function checkUsernameExists(username) {
  const { data } = await client.get('/auth/exists', { params: { username } })
  return data
}

export async function searchUsers(query, limit = 8) {
  const { data } = await client.get('/auth/users/search', {
    params: { q: query, limit },
  })
  return data
}

export async function login(username, create = false) {
  const { data } = await client.post('/auth/login', { username, create })
  return data
}

export async function logout() {
  const { data } = await client.post('/auth/logout')
  return data
}

export async function fetchMe() {
  const { data } = await client.get('/auth/me')
  return data
}
