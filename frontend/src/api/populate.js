import client from './client'

export async function populateXml(request) {
  const { data } = await client.post('/populate', request)
  return data
}
