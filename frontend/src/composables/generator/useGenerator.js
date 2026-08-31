import { ref, computed, watch, onMounted, onActivated, onBeforeUnmount, nextTick } from 'vue'
import { listSchemas } from '../../api/dtd'
import { getConfigAliases } from '../../api/config'
import { stageFillXml } from '../../api/fill'
import { pickPrimarySchema, normalizeDtdUploadResult, normalizeDtdListResult } from '../../utils/dtdSchema'
import { clearAllDatalistState } from '../../utils/datalistInput'
import { formatElements } from '../../utils/ruPlural'
import { peekXmlRootElement } from '../../utils/xmlPaths'
import { translateApiError } from '../../utils/apiErrors'
import { extractPushWarnings } from '../../utils/gitPushWarnings'
import { useGenerationHistory } from '../useGenerationHistory'
import { useXmlLibrary } from '../useXmlLibrary'
import { useGeneratorLayout } from './useGeneratorLayout'
import { useGeneratorTabs, leftTabs } from './useGeneratorTabs'
import { useGeneratorMapping } from './useGeneratorMapping'
import { useGeneratorSchema } from './useGeneratorSchema'
import { useGeneratorXml } from './useGeneratorXml'
import { useGeneratorActions } from './useGeneratorActions'
import { useGeneratorCompare } from './useGeneratorCompare'
import { usesDbFill } from '../../utils/fillStrategies'

export function useGenerator() {
  const error = ref('')
  const fillStrategy = ref('ai')
  const structureTabRef = ref(null)
  const generatorRef = ref(null)
  const generating = ref(false)
  const filling = ref(false)
  const validating = ref(false)

  const isHybridStrategy = computed(() => usesDbFill(fillStrategy.value))

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

  async function onLoadLibraryDocument(xmlText) {
    xml.clearGenerationState()
    await xml.setProgrammaticXml(xmlText, { dirty: true })
    if (schema.schemaId.value) {
      await stageFillXml(schema.schemaId.value, xmlText)
      await xml.syncFromPastedXml(xmlText)
    }
  }

  const xmlLibrary = useXmlLibrary({ onLoadDocument: onLoadLibraryDocument })
  const categoryDocuments = ref({})
  const loadingCategory = ref(null)

  const canSaveLibraryDocument = computed(
    () => Boolean(xml.getEditorXmlText()?.trim() || xml.xmlText.value?.trim()),
  )

  const gitPushEnabled = computed(() => {
    const status = xmlLibrary.syncStatus.value
    if (!status?.push_enabled) return false
    if (status.git_auth_required && !status.git_configured) return false
    return true
  })

  const gitPushMessage = ref('')
  const gitPushError = ref('')
  const gitPushWarnings = ref([])
  const gitPushWarningCount = ref(0)

  function resetGitPushFeedback() {
    gitPushMessage.value = ''
    gitPushError.value = ''
    gitPushWarnings.value = []
    gitPushWarningCount.value = 0
  }

  function clearGitPushWarnings() {
    gitPushWarnings.value = []
    gitPushWarningCount.value = 0
  }

  async function handleGitPush({ filename, commitMessage, acknowledgeWarnings = false }) {
    const xmlText = xml.getEditorXmlText() || xml.xmlText.value || ''
    const peekedRoot = peekXmlRootElement(xmlText)
    const rootElement = peekedRoot || schema.rootElement.value
    const schemaId = schema.schemaId.value
    if (!rootElement) {
      gitPushError.value = 'Не удалось определить корневой элемент документа'
      return
    }
    if (!schemaId) {
      gitPushError.value = 'Выберите DTD-схему перед отправкой в Git'
      return
    }
    gitPushMessage.value = ''
    gitPushError.value = ''
    if (!acknowledgeWarnings) clearGitPushWarnings()
    try {
      const result = await xmlLibrary.pushToGit({
        rootElement,
        filename,
        xmlText,
        schemaId,
        commitMessage,
        acknowledgeWarnings,
      })
      clearGitPushWarnings()
      if (result?.status === 'ok') {
        gitPushMessage.value = result.overwritten
          ? `Файл обновлён: ${result.path}`
          : `Файл добавлен: ${result.path}`
        categoryDocuments.value = {}
      } else if (result?.status === 'unchanged') {
        gitPushMessage.value = result.message || 'Изменений нет'
      }
    } catch (err) {
      const pending = extractPushWarnings(err)
      if (pending) {
        gitPushWarnings.value = pending.warnings
        gitPushWarningCount.value = pending.warningCount
        gitPushError.value = ''
        return
      }
      gitPushError.value = translateApiError(
        err?.message || err?.response?.data?.detail || String(err),
      )
    }
  }

  async function handleLibraryExpandCategory(category) {
    loadingCategory.value = category
    try {
      await xmlLibrary.loadCategoryDocuments(category)
      categoryDocuments.value = {
        ...categoryDocuments.value,
        [category]: [...xmlLibrary.sharedDocuments.value],
      }
    } finally {
      loadingCategory.value = null
    }
  }

  async function handleLibrarySync() {
    try {
      await xmlLibrary.syncFromGit()
      categoryDocuments.value = {}
    } catch {
      // Error surfaced via libraryError.
    }
  }

  async function handleLibrarySave({ name, description }) {
    const xmlText = xml.getEditorXmlText() || xml.xmlText.value || ''
    try {
      await xmlLibrary.saveCurrentDocument({
        name,
        schemaId: schema.schemaId.value,
        xmlText,
        description,
      })
    } catch (err) {
      xmlLibrary.libraryError.value = err?.response?.data?.detail || err?.message || String(err)
    }
  }

  async function handleLibraryDeletePersonal(name) {
    try {
      await xmlLibrary.removePersonalDocument(name)
    } catch (err) {
      xmlLibrary.libraryError.value = err?.response?.data?.detail || err?.message || String(err)
    }
  }

  const shareDialogOpen = ref(false)
  const shareDialogMode = ref('personal')
  const shareDialogDocumentName = ref('')
  const shareDialogSubmitting = ref(false)
  const shareDialogError = ref('')

  function openSharePersonalDialog(name) {
    shareDialogMode.value = 'personal'
    shareDialogDocumentName.value = name
    shareDialogError.value = ''
    shareDialogOpen.value = true
  }

  function openShareInlineDialog() {
    shareDialogMode.value = 'inline'
    shareDialogDocumentName.value = ''
    shareDialogError.value = ''
    shareDialogOpen.value = true
  }

  function closeShareDialog() {
    if (shareDialogSubmitting.value) return
    shareDialogOpen.value = false
    shareDialogError.value = ''
  }

  async function handleShareSubmit({ recipientUsername, message, name }) {
    shareDialogSubmitting.value = true
    shareDialogError.value = ''
    try {
      if (shareDialogMode.value === 'personal') {
        await xmlLibrary.sharePersonalDocument(
          shareDialogDocumentName.value,
          recipientUsername,
          message,
        )
      } else {
        const xmlText = xml.getEditorXmlText() || xml.xmlText.value || ''
        await xmlLibrary.shareCurrentDocument({
          name: name || shareDialogDocumentName.value,
          schemaId: schema.schemaId.value,
          xmlText,
          recipientUsername,
          message,
        })
      }
      shareDialogOpen.value = false
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (detail && typeof detail === 'object') {
        shareDialogError.value = translateApiError(detail.message || 'Пользователь не найден')
      } else {
        shareDialogError.value = translateApiError(detail || err?.message || String(err))
      }
    } finally {
      shareDialogSubmitting.value = false
    }
  }

  watch(tabs.activeTab, (tab) => {
    if (tab === 'library') {
      xmlLibrary.refreshSharedCategories()
      xmlLibrary.refreshPersonalDocuments()
    }
  })

  const actions = useGeneratorActions({
    schemaId: schema.schemaId,
    rootElement: schema.rootElement,
    mode: schema.mode,
    repeatCount: schema.repeatCount,
    repeatOverrides: schema.repeatOverrides,
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
    preserveFilled: tabs.preserveFilled,
    getEditorXmlText: xml.getEditorXmlText,
    setProgrammaticXml: xml.setProgrammaticXml,
    addHistoryEntry,
    focusResultsTab: tabs.focusResultsTab,
  })

  const compare = useGeneratorCompare({
    getEditorXmlText: xml.getEditorXmlText,
    xmlEditorRef: xml.xmlEditorRef,
    llmAlias: mapping.llmAlias,
    elementDocs: schema.elementDocs,
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

  async function onEditorClear() {
    await xml.onEditorClear()
    clearAllDatalistState()
    error.value = ''
    schema.rootElement.value = ''
    schema.mode.value = 'minimal'
    schema.repeatCount.value = 1
    schema.repeatOverrides.value = {}
    schema.customPaths.value = []
    mapping.resetMappings()
    mapping.mappingPresetName.value = ''
    compare.clearCompareReport()
    tabs.focusStructureTab()
  }

  watch(mapping.wizardOpen, async (isOpen) => {
    if (isOpen) {
      await nextTick()
      xml.liveXmlText.value = xml.getEditorXmlText() || xml.xmlText.value || ''
    }
  })

  async function refreshConnectionAliases() {
    const aliases = await getConfigAliases().catch(() => null)
    if (!aliases) return

    mapping.dbAliases.value = aliases.databases || []
    mapping.llmAliases.value = aliases.llm || []
    mapping.defaultLlmAlias.value = aliases.default_llm || ''

    const available = mapping.llmAliases.value
    const current = mapping.llmAlias.value
    if (current && available.includes(current)) return

    mapping.llmAlias.value = mapping.defaultLlmAlias.value || available[0] || ''
  }

  onMounted(async () => {
    // Run config-aliases fetch concurrently with schema loading so that LLM/DB
    // aliases are available as soon as possible (avoids a race where the user
    // triggers compare before aliases are populated).
    const aliasesPromise = refreshConnectionAliases()

    try {
      const listResult = normalizeDtdListResult(await listSchemas())
      const primary = pickPrimarySchema(listResult.schemas)
      if (primary) {
        await onDtdUploaded(
          normalizeDtdUploadResult({
            schemas: listResult.schemas,
            primary_schema_id: primary.schema_id,
            import_source: listResult.import_source,
            updated_at: listResult.updated_at,
            source_type: listResult.source_type,
            resolved_version: listResult.resolved_version,
          }),
        )
      }
    } catch {
      // No saved schemas or API unavailable.
    }

    await aliasesPromise

    await xmlLibrary.refreshSharedCategories()
    await xmlLibrary.refreshPersonalDocuments()
  })

  // GeneratorView is kept alive — refresh aliases when returning from Settings
  // (e.g. after deleting and recreating an LLM alias).
  let skipNextActivationRefresh = true
  onActivated(() => {
    if (skipNextActivationRefresh) {
      skipNextActivationRefresh = false
      return
    }
    refreshConnectionAliases()
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
    onDocumentPaste: xml.onDocumentPaste,
    libraryActiveScope: xmlLibrary.activeScope,
    sharedCategories: xmlLibrary.sharedCategories,
    personalDocuments: xmlLibrary.personalDocuments,
    syncStatus: xmlLibrary.syncStatus,
    librarySyncing: xmlLibrary.syncing,
    libraryLoading: xmlLibrary.loading,
    gitPushSubmitting: xmlLibrary.gitPushing,
    libraryError: xmlLibrary.libraryError,
    canSaveLibraryDocument,
    gitPushEnabled,
    gitPushMessage,
    gitPushError,
    gitPushWarnings,
    gitPushWarningCount,
    resetGitPushFeedback,
    handleGitPush,
    categoryDocuments,
    loadingCategory,
    handleLibrarySync,
    handleLibraryExpandCategory,
    handleLibraryOpenShared: xmlLibrary.openSharedDocument,
    handleLibraryOpenPersonal: xmlLibrary.openPersonalDocument,
    handleLibrarySave,
    handleLibraryDeletePersonal,
    shareDialogOpen,
    shareDialogMode,
    shareDialogDocumentName,
    shareDialogSubmitting,
    shareDialogError,
    openSharePersonalDialog,
    openShareInlineDialog,
    closeShareDialog,
    handleShareSubmit,
    ...schema,
    ...mapping,
    ...xml,
    onEditorClear,
    ...tabs,
    ...actions,
    ...compare,
    generating,
    filling,
    validating,
  }
}
