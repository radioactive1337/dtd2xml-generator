import client from './client'

export async function analyzeStructure(xmlText) {
  const { data } = await client.post('/xml-compare/structure', {
    xml_text: xmlText,
  })
  return data
}

export async function explainStructure({
  rootElement,
  uniquePaths,
  closest,
  snippets,
  llmAlias,
}) {
  const payload = {
    root_element: rootElement || '',
    unique_paths: uniquePaths || [],
    closest: closest || null,
    snippets: snippets || [],
  }
  if (llmAlias) {
    payload.llm_alias = llmAlias
  }
  const { data } = await client.post('/xml-compare/explain', payload)
  return data
}
