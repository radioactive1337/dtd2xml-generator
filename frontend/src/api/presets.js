import client from './client'

export async function listPresets() {
  const { data } = await client.get('/presets')
  return data
}

export async function savePreset(preset) {
  const { data } = await client.post('/presets', preset)
  return data
}

export async function loadPreset(name) {
  const { data } = await client.get(`/presets/${encodeURIComponent(name)}`)
  return data
}

export async function deletePreset(name) {
  const { data } = await client.delete(`/presets/${encodeURIComponent(name)}`)
  return data
}

export async function sharePreset({ recipientUsername, sourcePresetName, message = '' }) {
  const { data } = await client.post('/presets/share', {
    recipient_username: recipientUsername,
    source_preset_name: sourcePresetName,
    message,
  })
  return data
}
