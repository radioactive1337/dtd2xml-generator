import client from './client'

// NOTE: request bodies carry real personal data. Nothing here may be logged,
// cached or persisted on the client side.

export async function getAnonymizeCategories() {
  const { data } = await client.get('/anonymize/categories')
  return data.categories || []
}

export async function analyzeXml(payload) {
  const { data } = await client.post('/anonymize/analyze', payload)
  return data
}

export async function applyAnonymization(payload) {
  const { data } = await client.post('/anonymize/apply', payload)
  return data
}

export async function getAnonymizeRules() {
  const { data } = await client.get('/anonymize/rules')
  return data
}

export async function upsertAnonymizeRules(rules) {
  const { data } = await client.post('/anonymize/rules/upsert', { rules })
  return data
}

export async function deleteAnonymizeRule(ruleId) {
  const { data } = await client.delete(`/anonymize/rules/${encodeURIComponent(ruleId)}`)
  return data
}

export async function clearAnonymizeRules() {
  const { data } = await client.delete('/anonymize/rules')
  return data
}

export async function importAnonymizeRules(rules, mode = 'merge') {
  const { data } = await client.post('/anonymize/rules/import', { rules, mode })
  return data
}

export async function exportAnonymizeRules(layer = 'user') {
  const { data } = await client.get('/anonymize/rules/export', { params: { layer } })
  return data
}

export async function suggestCategories(payload) {
  const { data } = await client.post('/anonymize/suggest-categories', payload)
  return data
}
