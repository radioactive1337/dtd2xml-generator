import client from './client'

export async function listMappingPresets(schemaId) {
  const params = schemaId ? { schema_id: schemaId } : {}
  const { data } = await client.get('/mapping-presets', { params })
  return data
}

export async function saveMappingPreset(preset) {
  const { data } = await client.post('/mapping-presets', preset)
  return data
}

export async function loadMappingPreset(name) {
  const { data } = await client.get(`/mapping-presets/${encodeURIComponent(name)}`)
  return data
}

export async function deleteMappingPreset(name) {
  const { data } = await client.delete(`/mapping-presets/${encodeURIComponent(name)}`)
  return data
}
