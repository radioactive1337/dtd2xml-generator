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

function normalizeImportFields(rawFields) {
  if (!rawFields) return []
  if (Array.isArray(rawFields)) {
    return rawFields.map((field) => ({
      db_col: field?.db_col || '',
      xml_attr: field?.xml_attr || '',
    }))
  }
  if (typeof rawFields === 'object') {
    return Object.entries(rawFields).map(([db_col, xml_attr]) => ({
      db_col,
      xml_attr: xml_attr || '',
    }))
  }
  return []
}

function normalizeImportMapping(mapping, legacyDbAlias = '') {
  return {
    target_element: mapping?.target_element || '',
    target_path: mapping?.target_path || '',
    query: mapping?.query || '',
    db_alias: mapping?.db_alias || legacyDbAlias || '',
    fields: normalizeImportFields(mapping?.fields),
  }
}

export function parseMappingPresetFile(text) {
  let data
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error('Некорректный JSON')
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('JSON должен содержать объект пресета')
  }

  const name = typeof data.name === 'string' ? data.name.trim() : ''
  if (!name) throw new Error('В пресете не указано имя (name)')
  if (!Array.isArray(data.mappings)) {
    throw new Error('В пресете отсутствует список mappings')
  }

  const legacyDbAlias = data.db_alias || ''
  return {
    name,
    schema_id: data.schema_id || '',
    mappings: data.mappings.map((mapping) => normalizeImportMapping(mapping, legacyDbAlias)),
  }
}

function safeDownloadName(name) {
  const safe = String(name || '').trim().replace(/[\\/:*?"<>|]+/g, '_')
  return safe || 'mapping-preset'
}

function downloadJsonFile(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export async function exportMappingPreset(name) {
  const preset = await loadMappingPreset(name)
  downloadJsonFile(`${safeDownloadName(preset.name)}.json`, preset)
  return preset
}
