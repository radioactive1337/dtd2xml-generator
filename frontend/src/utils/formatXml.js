import xmlFormat from 'xml-formatter'

export function formatXml(xml) {
  if (!xml?.trim()) return xml || ''
  return xmlFormat(xml, {
    indentation: '  ',
    lineSeparator: '\n',
    throwOnFailure: false,
  })
}

export function registerXmlFormatter(monaco) {
  monaco.languages.registerDocumentFormattingEditProvider('xml', {
    async provideDocumentFormattingEdits(model) {
      const source = model.getValue()
      const formatted = formatXml(source)
      if (formatted === source) return []
      return [{ range: model.getFullModelRange(), text: formatted }]
    },
  })
}
