const API_ERROR_MESSAGES = {
  'Database alias not found': 'Алиас БД не найден',
  "Database alias '{alias}' not found in connections.json": 'Алиас БД не найден в connections.json',
  'SQL query is required': 'Укажите SQL-запрос',
  'Only SELECT queries are allowed': 'Разрешены только SELECT-запросы',
  'Streaming is not supported by this browser': 'Браузер не поддерживает потоковую передачу',
  'Fill failed': 'Ошибка заполнения',
  'Fill stream ended without a result': 'Поток заполнения завершился без результата',
  'Unknown error': 'Неизвестная ошибка',
}

export function translateApiError(message) {
  if (!message || typeof message !== 'string') return message
  if (API_ERROR_MESSAGES[message]) return API_ERROR_MESSAGES[message]

  const dbAliasMatch = message.match(/^Database alias '([^']+)' not found/)
  if (dbAliasMatch) {
    return `Алиас БД «${dbAliasMatch[1]}» не найден`
  }

  const queryFailedMatch = message.match(/^Query failed: (.+)$/)
  if (queryFailedMatch) {
    return `Ошибка запроса: ${queryFailedMatch[1]}`
  }

  return message
}
