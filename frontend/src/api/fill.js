import client from './client'

export async function fillXml(request) {
  const { data } = await client.post('/fill', request)
  return data
}
