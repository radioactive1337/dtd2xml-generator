import { ref, computed, watch, nextTick } from 'vue'
import {
  canonicalizeXmlElementName,
  canonicalizeXmlElementPaths,
  extractXmlElementPaths,
} from '../../utils/xmlPaths'

export function useGeneratorXml({
  schemaId,
  elements,
  rootElement,
  mode,
  dtdElementPaths,
  structureTabRef,
  generating,
  filling,
  dtdCollapsed,
}) {
  const xmlText = ref('')
  const xmlDirty = ref(false)
  const liveXmlText = ref('')
  const buildInfo = ref(null)
  const validationResult = ref(null)
  const xmlSyncHint = ref('')
  const xmlEditorRef = ref(null)

  let ignoreNextXmlWatch = false
  let skipModeSync = false

  const availableElementPaths = computed(() => {
    const text = (liveXmlText.value || xmlText.value || '').trim()
    if (!text) return dtdElementPaths.value
    try {
      const parsed = extractXmlElementPaths(text, { skipFormat: true })
      if (parsed?.elementPaths?.length) {
        return canonicalizeXmlElementPaths(parsed.elementPaths, elements.value)
      }
    } catch {
      // malformed or partial XML in editor
    }
    return dtdElementPaths.value
  })

  watch(mode, async (val, oldVal) => {
    if (val === 'custom') {
      dtdCollapsed.value = true
      if (!skipModeSync && oldVal !== 'custom' && getEditorXmlText()?.trim()) {
        await nextTick()
        await applyXmlPathsFromEditor(getEditorXmlText())
      }
    } else if (!schemaId.value) {
      dtdCollapsed.value = false
    }
  })

  function goToValidationError(err) {
    if (!err?.line) return
    xmlEditorRef.value?.goToPosition(err.line, err.column)
  }

  function getEditorXmlText() {
    return xmlEditorRef.value?.getValue?.() ?? xmlText.value
  }

  async function setProgrammaticXml(text, { dirty = false } = {}) {
    ignoreNextXmlWatch = true
    const xml = text || ''
    liveXmlText.value = xml
    xmlText.value = xml
    xmlDirty.value = dirty
    await nextTick()
    xmlEditorRef.value?.setValue?.(xml)
    ignoreNextXmlWatch = false
  }

  function onEditorContentChange(text) {
    if (ignoreNextXmlWatch || generating.value || filling.value) return
    liveXmlText.value = text || ''
    xmlText.value = text || ''
    xmlDirty.value = true
  }

  async function onXmlFileImported({ text }) {
    validationResult.value = null
    buildInfo.value = null
    await setProgrammaticXml(text, { dirty: true })
    if (schemaId.value) {
      await syncFromPastedXml(text)
    }
  }

  async function waitForDtdTreeRef(maxAttempts = 5) {
    for (let i = 0; i < maxAttempts; i += 1) {
      const treeRef = structureTabRef.value?.dtdTreeRef
      if (treeRef) return treeRef
      await nextTick()
    }
    return structureTabRef.value?.dtdTreeRef
  }

  async function applyXmlPathsFromEditor(text) {
    const trimmed = text?.trim()
    if (!trimmed) {
      xmlSyncHint.value = ''
      return
    }

    try {
      const parsed = extractXmlElementPaths(trimmed)
      if (!parsed) return

      const { rootTag, elementPaths } = parsed
      const canonicalRootTag = canonicalizeXmlElementName(rootTag, elements.value)
      const canonicalElementPaths = canonicalizeXmlElementPaths(elementPaths, elements.value)

      if (!rootTag) {
        xmlSyncHint.value = 'В XML нет корневого элемента — выберите корень вручную'
        return
      }

      if (!elements.value.includes(canonicalRootTag)) {
        xmlSyncHint.value = `Корневой элемент «${rootTag}» не описан в DTD`
        return
      }

      xmlSyncHint.value = ''
      if (canonicalRootTag && rootElement.value !== canonicalRootTag) {
        rootElement.value = canonicalRootTag
        await nextTick()
      }
      const treeRef = await waitForDtdTreeRef()
      await treeRef?.applyXmlElementPaths(canonicalElementPaths)
    } catch (e) {
      xmlSyncHint.value = e.message || 'Не удалось разобрать пути элементов в XML'
    }
  }

  async function syncFromPastedXml(text) {
    const trimmed = text?.trim()
    if (!trimmed) {
      xmlSyncHint.value = ''
      return
    }

    try {
      const parsed = extractXmlElementPaths(trimmed)
      if (!parsed) return

      const { rootTag } = parsed
      const canonicalRootTag = canonicalizeXmlElementName(rootTag, elements.value)

      if (!rootTag) {
        xmlSyncHint.value = 'В XML нет корневого элемента — выберите корень вручную'
        return
      }

      if (!elements.value.includes(canonicalRootTag)) {
        xmlSyncHint.value = `Корневой элемент «${rootTag}» не описан в DTD`
        return
      }

      xmlSyncHint.value = ''
      skipModeSync = true
      mode.value = 'custom'
      await nextTick()
      skipModeSync = false
      await waitForDtdTreeRef()
      await applyXmlPathsFromEditor(text)
    } catch (e) {
      xmlSyncHint.value = e.message || 'Не удалось синхронизировать XML из редактора'
    }
  }

  async function restoreFromHistory(entry, clearError) {
    if (!entry?.xml_text) return
    validationResult.value =
      entry.validation_valid === true ? { valid: true, errors: [] } : null
    buildInfo.value =
      entry.node_count != null
        ? { node_count: entry.node_count, warnings: entry.warnings || [] }
        : null
    xmlSyncHint.value = ''
    if (clearError) clearError.value = ''
    await setProgrammaticXml(entry.xml_text, { dirty: true })
  }

  function clearGenerationState() {
    buildInfo.value = null
    validationResult.value = null
    xmlSyncHint.value = ''
  }

  function dispose() {}

  return {
    xmlText,
    xmlDirty,
    liveXmlText,
    buildInfo,
    validationResult,
    xmlSyncHint,
    xmlEditorRef,
    availableElementPaths,
    goToValidationError,
    getEditorXmlText,
    setProgrammaticXml,
    onEditorContentChange,
    onXmlFileImported,
    syncFromPastedXml,
    restoreFromHistory,
    clearGenerationState,
    dispose,
  }
}
