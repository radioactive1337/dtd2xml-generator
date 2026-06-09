import client from './client'

export async function generateXml(config) {
  const { data } = await client.post('/generate', config)
  return data
}
