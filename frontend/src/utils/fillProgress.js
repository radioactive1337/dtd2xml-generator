const FILL_STEP_MESSAGES = {
  started: 'Подготовка…',
  accepted: 'Подготовка…',
  xml_upload: 'Загрузка XML…',
  db_query: 'Запрос к БД…',
  db_done: 'Данные из БД применены',
  faker: 'Генерация через Faker…',
  llm_request: 'Ожидание ответа LLM…',
  llm_prepare: 'Подготовка запросов к LLM…',
  llm_merge: 'Объединение ответа LLM…',
  faker_fallback: 'Дозаполнение через Faker…',
  complete: 'Заполнение завершено',
  cancelled: 'Заполнение отменено',
}

export function translateFillStep(step) {
  return FILL_STEP_MESSAGES[step] ?? null
}
