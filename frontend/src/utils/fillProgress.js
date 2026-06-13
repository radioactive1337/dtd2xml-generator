const FILL_STEP_MESSAGES = {
  started: 'Подготовка…',
  db_query: 'Запрос к БД…',
  db_done: 'Данные из БД применены',
  faker: 'Генерация через Faker…',
  llm_request: 'Ожидание ответа LLM…',
  llm_merge: 'Объединение ответа LLM…',
  complete: 'Заполнение завершено',
}

export function translateFillStep(step) {
  return FILL_STEP_MESSAGES[step] ?? null
}
