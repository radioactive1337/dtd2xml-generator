/** Russian plural: 1 / 2–4 / 5+ (with 11–14 exceptions). */
function pluralRu(n, one, few, many) {
  const abs = Math.abs(n)
  const mod10 = abs % 10
  const mod100 = abs % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

export function formatCount(n, one, few, many) {
  return `${n} ${pluralRu(n, one, few, many)}`
}

export function formatElements(n) {
  return formatCount(n, 'элемент', 'элемента', 'элементов')
}

export function formatNodes(n) {
  return formatCount(n, 'узел', 'узла', 'узлов')
}

export function formatErrors(n) {
  return formatCount(n, 'ошибка', 'ошибки', 'ошибок')
}

export function formatWarnings(n) {
  return formatCount(n, 'предупреждение', 'предупреждения', 'предупреждений')
}

export function formatMappings(n) {
  return formatCount(n, 'маппинг', 'маппинга', 'маппингов')
}
