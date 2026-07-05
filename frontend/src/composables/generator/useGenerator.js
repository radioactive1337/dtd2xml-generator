import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { listSchemas } from '../../api/dtd'
import { getConfigAliases } from '../../api/config'
import { pickPrimarySchema } from '../../utils/dtdSchema'
import { clearAllDatalistState } from '../../utils/datalistInput'
import { formatElements } from '../../utils/ruPlural'
import { useGenerationHistory } from '../useGenerationHistory'
import { useGeneratorLayout } from './useGeneratorLayout'
import { useGeneratorTabs, leftTabs } from './useGeneratorTabs'
import { useGeneratorMapping } from './useGeneratorMapping'
import { useGeneratorSchema } from './useGeneratorSchema'
import { useGeneratorXml } from './useGeneratorXml'
import { useGeneratorActions } from './useGeneratorActions'

export function useGenerator() {
  const error = ref('')
  const fillStrategy = ref('faker')
  const structureTabRef = ref(null)
  const generatorRef = ref(null)
  const generating = ref(false)
  const filling = ref(false)
  const validating = ref(false)

  const isHybridStrategy = computed(
    () => fillStrategy.value === 'hybrid_db_faker' || fillStrategy.value === 'hybrid_db_ai',
  )

  const { leftWidth, dtdCollapsed, startHResize } = useGeneratorLayout()
  const schema = useGeneratorSchema()

  const mapping = useGeneratorMapping({
    schemaId: schema.schemaId,
    elements: schema.elements,
    error,
    isHybridStrategy,
    fillStrategy,
  })

  const xml = useGeneratorXml({
    schemaId: schema.schemaId,
    elements: schema.elements,
    rootElement: schema.rootElement,
    mode: schema.mode,
    dtdElementPaths: schema.dtdElementPaths,
    structureTabRef,
    generating,
    filling,
    dtdCollapsed,
  })

  const {
    history: generationHistory,
    addEntry: addHistoryEntry,
    removeEntry: removeHistoryEntry,
    clearHistory: clearGenerationHistory,
    maxEntries: historyMaxEntries,
  } = useGenerationHistory()

  const tabs = useGeneratorTabs({
    hasMappingBlockers: mapping.hasMappingBlockers,
    hasLlmBlocker: mapping.hasLlmBlocker,
    isHybridStrategy,
    sqlMappings: mapping.sqlMappings,
    validationResult: xml.validationResult,
    buildInfo: xml.buildInfo,
    xmlSyncHint: xml.xmlSyncHint,
    fillStrategy,
  })

  const actions = useGeneratorActions({
    schemaId: schema.schemaId,
    rootElement: schema.rootElement,
    mode: schema.mode,
    repeatCount: schema.repeatCount,
    customPaths: schema.customPaths,
    fillStrategy,
    llmAlias: mapping.llmAlias,
    isHybridStrategy,
    sqlMappings: mapping.sqlMappings,
    xmlText: xml.xmlText,
    xmlDirty: xml.xmlDirty,
    buildInfo: xml.buildInfo,
    validationResult: xml.validationResult,
    xmlSyncHint: xml.xmlSyncHint,
    error,
    generating,
    filling,
    validating,
    autoValidateAfterFill: tabs.autoValidateAfterFill,
    getEditorXmlText: xml.getEditorXmlText,
    setProgrammaticXml: xml.setProgrammaticXml,
    addHistoryEntry,
    focusResultsTab: tabs.focusResultsTab,
  })

  const elementCountLabel = computed(() => formatElements(schema.dtdMeta.value.elementCount))

  async function onDtdUploaded(result) {
    await schema.applyDtdUpload(result)
    mapping.resetMappings()
    if (isHybridStrategy.value) await mapping.refreshMappingPresets()
    xml.clearGenerationState()
    error.value = ''
    dtdCollapsed.value = true
    tabs.focusStructureTab()
    tabs.resetHybridTabSwitch()

    await nextTick()
    const editorXml = xml.getEditorXmlText()?.trim()
    if (editorXml) {
      await xml.setProgrammaticXml(editorXml)
      await xml.syncFromPastedXml(editorXml)
      return
    }
    await xml.setProgrammaticXml('')
  }

  watch(mapping.wizardOpen, async (isOpen) => {
    if (isOpen) {
      await nextTick()
      xml.liveXmlText.value = xml.getEditorXmlText() || xml.xmlText.value || ''
    }
  })

  onMounted(async () => {
    try {
      const schemas = await listSchemas()
      const primary = pickPrimarySchema(schemas)
      if (primary) await onDtdUploaded(primary)
    } catch {
      // No saved schemas or API unavailable.
    }

    try {
      const aliases = await getConfigAliases()
      mapping.dbAliases.value = aliases.databases || []
      mapping.llmAliases.value = aliases.llm || []
      mapping.defaultLlmAlias.value = aliases.default_llm || ''
      mapping.llmAlias.value = mapping.defaultLlmAlias.value || mapping.llmAliases.value[0] || ''
    } catch {
      mapping.dbAliases.value = []
      mapping.llmAliases.value = []
      mapping.defaultLlmAlias.value = ''
      mapping.llmAlias.value = ''
    }
  })

  onBeforeUnmount(() => {
    xml.dispose()
    mapping.dispose()
    actions.dispose()
    clearAllDatalistState()
  })

  return {
    generatorRef,
    structureTabRef,
    leftWidth,
    dtdCollapsed,
    startHResize,
    leftTabs,
    error,
    fillStrategy,
    isHybridStrategy,
    elementCountLabel,
    generationHistory,
    historyMaxEntries,
    removeHistoryEntry,
    clearGenerationHistory,
    onDtdUploaded,
    restoreFromHistory: (entry) => xml.restoreFromHistory(entry, error),
    goToValidationError: xml.goToValidationError,
    onEditorContentChange: xml.onEditorContentChange,
    onXmlFileImported: xml.onXmlFileImported,
    ...schema,
    ...mapping,
    ...xml,
    ...tabs,
    ...actions,
    generating,
    filling,
    validating,
  }
}
