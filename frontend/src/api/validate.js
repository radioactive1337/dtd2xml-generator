import client from './client'

export async function validateXml(schemaId, xmlText) {
  const { data } = await client.post('/validate', {
    schema_id: schemaId,
    xml_text: xmlText,
  })
  return data
}
