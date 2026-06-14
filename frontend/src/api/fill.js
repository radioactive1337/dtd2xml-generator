import client from './client'
import { translateApiError } from '../utils/apiErrors'
import { translateFillStep } from '../utils/fillProgress'

export async function fillXml(request) {
  const { data } = await client.post('/fill', request)
  return data
}

export async function stageFillXml(schemaId, xmlText) {
  await client.put('/fill/xml-cache', {
    schema_id: schemaId,
    xml_text: xmlText,
  })
}

export async function suggestFieldMappingsAi({
  schemaId,
  targetElement,
  columns,
  existingMappings = [],
  llmAlias,
}) {
  const payload = {
    schema_id: schemaId,
    target_element: targetElement,
    columns,
    existing_mappings: existingMappings,
  }
  if (llmAlias) {
    payload.llm_alias = llmAlias
  }
  const { data } = await client.post('/fill/suggest-field-mappings', payload)
  return data
}

function parseSseChunk(buffer) {
  const events = []
  const parts = buffer.split('\n\n')
  const remainder = parts.pop() ?? ''

  for (const part of parts) {
    const line = part
      .split('\n')
      .find((entry) => entry.startsWith('data: '))
    if (!line) continue
    try {
      events.push(JSON.parse(line.slice(6)))
    } catch {
      // Ignore malformed SSE payloads.
    }
  }

  return { events, remainder }
}

/**
 * Fill XML via SSE stream. Calls onProgress({ step, message, percent }) for each stage.
 * Resolves with { xml_text, strategy } on success.
 */
export async function fillXmlStream(request, onProgress) {
  const response = await fetch('/api/fill/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch {
      // Keep default status text.
    }
    const detailText = typeof detail === 'string' ? detail : JSON.stringify(detail)
    throw new Error(translateApiError(detailText))
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error(translateApiError('Streaming is not supported by this browser'))
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let result = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const { events, remainder } = parseSseChunk(buffer)
    buffer = remainder

    for (const event of events) {
      if (event.step === 'complete') {
        result = {
          xml_text: event.xml_text,
          strategy: request.strategy,
        }
        onProgress?.({
          step: 'complete',
          message: translateFillStep('complete'),
          percent: 100,
        })
        continue
      }

      if (event.step === 'error') {
        throw new Error(translateApiError(event.message || 'Fill failed'))
      }

      onProgress?.({
        step: event.step,
        message: translateFillStep(event.step) || event.message,
        percent: event.percent ?? 0,
      })
    }
  }

  if (!result?.xml_text) {
    throw new Error(translateApiError('Fill stream ended without a result'))
  }

  return result
}
