import { ref, watch } from 'vue'
import { listElements, getElementTree } from '../../api/dtd'
import { schemaFileName, normalizeDtdUploadResult, collectElementsFromSchemas } from '../../utils/dtdSchema'
import { collectDtdElementPaths } from '../../utils/mappingUtils'
import { loadRepeatablePaths } from '../../utils/repeatablePaths'

export function useGeneratorSchema() {
  const schemaId = ref('')
  const dtdMeta = ref({
    fileName: '',
    elementCount: 0,
    importSource: '',
    updatedAt: '',
  })
  const elements = ref([])
  const elementAttributes = ref({})
  const elementDocs = ref({})
  const elementAttributeDocs = ref({})
  const rootElement = ref('')
  const mode = ref('minimal')
  const repeatCount = ref(1)
  const repeatOverrides = ref({})
  const repeatablePaths = ref([])
  const customPaths = ref([])
  const dtdElementPaths = ref([])
  let repeatableRequestSeq = 0

  async function refreshRepeatablePaths() {
    const requestSeq = ++repeatableRequestSeq
    if (!schemaId.value || !rootElement.value || mode.value === 'minimal') {
      repeatablePaths.value = []
      return
    }
    try {
      const paths = await loadRepeatablePaths(schemaId.value, rootElement.value)
      if (requestSeq === repeatableRequestSeq) repeatablePaths.value = paths
    } catch {
      if (requestSeq === repeatableRequestSeq) repeatablePaths.value = []
    }
  }

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
    repeatOverrides.value = {}
  })

  watch([schemaId, rootElement, mode], () => {
    refreshRepeatablePaths()
    if (mode.value === 'minimal') repeatOverrides.value = {}
  })

  async function applyDtdUpload(result) {
    const primary = normalizeDtdUploadResult(result)
    const allSchemas = primary.schemas?.length ? primary.schemas : [primary]
    schemaId.value = primary.schema_id
    dtdMeta.value = {
      fileName: schemaFileName(primary),
      elementCount: collectElementsFromSchemas(allSchemas).length,
      schemaCount: allSchemas.length,
      importSource: primary.import_source || '',
      updatedAt: primary.updated_at || '',
    }
    elements.value = collectElementsFromSchemas(allSchemas)
    rootElement.value = ''
    try {
      const summaries = await listElements(primary.schema_id)
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
    repeatOverrides,
    repeatablePaths,
    customPaths,
    dtdElementPaths,
    applyDtdUpload,
  }
}
