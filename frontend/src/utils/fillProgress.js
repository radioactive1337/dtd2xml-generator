const FILL_STEP_MESSAGES = {
  started: 'Подготовка…',
  accepted: 'Подготовка…',
  xml_upload: 'Загрузка XML…',
  db_query: 'Запрос к БД…',
  db_done: 'Данные из БД применены',
  git_reference: 'Заполнение из Git-эталонов…',
  git_ai: 'Вариация значений из Git через LLM…',
  llm_request: 'Ожидание ответа LLM…',
  llm_prepare: 'Подготовка запросов к LLM…',
  llm_merge: 'Объединение ответа LLM…',
  complete: 'Заполнение завершено',
  cancelled: 'Заполнение отменено',
}

export function translateFillStep(step) {
  return FILL_STEP_MESSAGES[step] ?? null
}
