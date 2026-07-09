import client from './client'

export async function listMappingPresets() {
  const { data } = await client.get('/mapping-presets')
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

export async function shareMappingPreset({ recipientUsername, sourcePresetName, message = '' }) {
  const { data } = await client.post('/mapping-presets/share', {
    recipient_username: recipientUsername,
    source_preset_name: sourcePresetName,
    message,
  })
  return data
}
