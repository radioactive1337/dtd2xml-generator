/** Blank every attribute value in the given text: name="value" -> name="". */
export function clearAttributeValues(text) {
  return text.replace(
    /([\w:.-]+)(\s*=\s*)("[^"]*"|'[^']*')/g,
    (match, name, eq, quoted) => `${name}${eq}${quoted[0]}${quoted[0]}`,
  )
}
