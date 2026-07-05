import { ref, watch } from 'vue'
import { listElements, getElementTree } from '../../api/dtd'
import { schemaFileName } from '../../utils/dtdSchema'
import { collectDtdElementPaths } from '../../utils/mappingUtils'

export function useGeneratorSchema() {
  const schemaId = ref('')
  const dtdMeta = ref({ fileName: '', elementCount: 0 })
  const elements = ref([])
  const elementAttributes = ref({})
  const elementDocs = ref({})
  const elementAttributeDocs = ref({})
  const rootElement = ref('')
  const mode = ref('minimal')
  const repeatCount = ref(1)
  const customPaths = ref([])
  const dtdElementPaths = ref([])

  async function refreshDtdElementPaths() {
    if (!schemaId.value || !rootElement.value) {
      dtdElementPaths.value = []
      return
    }
    try {
      const data = await getElementTree(schemaId.value, rootElement.value)
      dtdElementPaths.value = collectDtdElementPaths(
        rootElement.value,
        data.content_model,
      )
    } catch {
      dtdElementPaths.value = []
    }
  }

  watch([schemaId, rootElement], () => {
    refreshDtdElementPaths()
  })

  async function applyDtdUpload(result) {
    schemaId.value = result.schema_id
    dtdMeta.value = {
      fileName: schemaFileName(result),
      elementCount: result.element_count,
    }
    elements.value = result.elements
    rootElement.value = ''
    try {
      const summaries = await listElements(result.schema_id)
      elementAttributes.value = Object.fromEntries(summaries.map((s) => [s.name, s.attributes]))
      elementDocs.value = Object.fromEntries(
        summaries.filter((s) => s.doc).map((s) => [s.name, s.doc]),
      )
      elementAttributeDocs.value = Object.fromEntries(
        summaries
          .filter((s) => s.attribute_docs && Object.keys(s.attribute_docs).length)
          .map((s) => [s.name, s.attribute_docs]),
      )
    } catch {
      elementAttributes.value = {}
      elementDocs.value = {}
      elementAttributeDocs.value = {}
    }
  }

  return {
    schemaId,
    dtdMeta,
    elements,
    elementAttributes,
    elementDocs,
    elementAttributeDocs,
    rootElement,
    mode,
    repeatCount,
    customPaths,
    dtdElementPaths,
    applyDtdUpload,
  }
}
