import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { listSchemas } from '../api/dtd'
import { getConfigAliases } from '../api/config'
import {
  analyzeXml,
  applyAnonymization,
  getAnonymizeCategories,
  suggestCategories,
} from '../api/anonymize'
import { pickPrimarySchema, normalizeDtdListResult } from '../utils/dtdSchema'
import { readXmlFileAsText } from '../utils/readXmlFile'
import {
  MAX_XML_CHARS,
  buildRequestPayload,
  buildRule,
  downloadFileName,
  isHandoffBlocked,
  reportStatus,
  safeErrorMessage,
} from '../utils/anonymize'
import { useAnonymizeHandoff } from './useAnonymizeHandoff'
import { useAnonymizeRules } from './useAnonymizeRules'
import { useXmlLibrary } from './useXmlLibrary'

const ANALYZE_DEBOUNCE_MS = 500
const SUGGEST_PAGE_SIZE = 150

/**
 * State of the anonymization page.
 *
 * Privacy: the source and the result XML live in component memory only.
 * They are never written to localStorage, the URL or the server (except the
 * explicit "save to My documents" action, which stores the *anonymized* text).
 */
export function useAnonymize() {
  const router = useRouter()
  const handoff = useAnonymizeHandoff()

  // -- source -----------------------------------------------------------
  const sourceXml = ref('')
  const sourceName = ref('')
  const sourceError = ref('')

  // -- settings ---------------------------------------------------------
  const schemas = ref([])
  const schemaId = ref('')
  const categories = ref([])
  const enabledCategories = ref([])
  const stripComments = ref(true)
  const consistency = ref('document')
  const seed = ref('')
  const useLlm = ref(false)
  const llmAlias = ref('')
  const llmAliases = ref([])

  // -- analysis / decisions --------------------------------------------
  const analysis = ref(null)
  const analyzing = ref(false)
  const analyzeError = ref('')
  const overrides = ref({})
  let analyzeSeq = 0
  let analyzeTimer = null

  // -- result -----------------------------------------------------------
  const result = ref(null)
  const applying = ref(false)
  const applyError = ref('')
  const resultStale = ref(false)
  const forceHandoff = ref(false)
  const showOriginal = ref(false)
  const actionMessage = ref('')

  // -- llm suggestions --------------------------------------------------
  const llmSuggestions = ref({})
  const suggesting = ref(false)
  const suggestProgress = ref('')
  const suggestError = ref('')
  let suggestCancelled = false

  const allCategoryIds = computed(() => categories.value.map((c) => c.id))
  const hasSource = computed(() => Boolean(sourceXml.value.trim()))
  const report = computed(() => result.value?.report || null)
  const resultXml = computed(() => result.value?.xml_text || '')
  const status = computed(() => reportStatus(report.value))
  const handoffBlocked = computed(
    () => !result.value || resultStale.value || isHandoffBlocked(report.value, forceHandoff.value),
  )
  const queue = computed(() => {
    const items = analysis.value?.unclassified || []
    return items.map((item) => ({
      ...item,
      ai_category: llmSuggestions.value[item.key] ?? item.llm_category ?? null,
    }))
  })
  const overrideCount = computed(() => Object.keys(overrides.value).length)
  const llmAvailable = computed(() => llmAliases.value.length > 0)

  const rules = useAnonymizeRules({ onChanged: () => analyzeNow() })

  const library = useXmlLibrary()

  function currentState() {
    return {
      xmlText: sourceXml.value,
      schemaId: schemaId.value,
      stripComments: stripComments.value,
      overrides: overrides.value,
      enabledCategories: enabledCategories.value,
      allCategoryIds: allCategoryIds.value,
    }
  }

  function markStale() {
    if (result.value) resultStale.value = true
  }

  // -- source handling --------------------------------------------------

  function setSource(text, name = '') {
    sourceError.value = ''
    if (text && text.length > MAX_XML_CHARS) {
      sourceError.value = 'Документ слишком большой (максимум 8 000 000 символов)'
      return
    }
    sourceXml.value = text || ''
    if (name) sourceName.value = name
    overrides.value = {}
    result.value = null
    resultStale.value = false
    forceHandoff.value = false
    showOriginal.value = false
    llmSuggestions.value = {}
    applyError.value = ''
    actionMessage.value = ''
    if (!hasSource.value) {
      analysis.value = null
      return
    }
    scheduleAnalyze(0)
  }

  async function importFile(file) {
    sourceError.value = ''
    try {
      const text = await readXmlFileAsText(file)
      if (!text.trim()) {
        sourceError.value = 'Файл пуст'
        return
      }
      setSource(text, file.name)
    } catch (err) {
      sourceError.value = safeErrorMessage(err) || 'Не удалось прочитать файл'
    }
  }

  function onSourceEdited(text) {
    if (text === sourceXml.value) return
    sourceXml.value = text || ''
    markStale()
    if (!hasSource.value) {
      analysis.value = null
      return
    }
    scheduleAnalyze()
  }

  function clearAll() {
    analyzeSeq += 1
    clearTimeout(analyzeTimer)
    suggestCancelled = true
    sourceXml.value = ''
    sourceName.value = ''
    sourceError.value = ''
    analysis.value = null
    analyzeError.value = ''
    overrides.value = {}
    result.value = null
    resultStale.value = false
    forceHandoff.value = false
    showOriginal.value = false
    applyError.value = ''
    actionMessage.value = ''
    llmSuggestions.value = {}
    suggestError.value = ''
    suggestProgress.value = ''
    seed.value = ''
  }

  // -- analysis ---------------------------------------------------------

  function scheduleAnalyze(delay = ANALYZE_DEBOUNCE_MS) {
    clearTimeout(analyzeTimer)
    analyzeTimer = setTimeout(() => {
      analyzeTimer = null
      void analyzeNow()
    }, delay)
  }

  async function analyzeNow() {
    clearTimeout(analyzeTimer)
    analyzeTimer = null
    if (!hasSource.value) {
      analysis.value = null
      return
    }
    const id = ++analyzeSeq
    analyzing.value = true
    analyzeError.value = ''
    try {
      const data = await analyzeXml(buildRequestPayload(currentState()))
      if (id !== analyzeSeq) return
      analysis.value = data
    } catch (err) {
      if (id !== analyzeSeq) return
      analysis.value = null
      analyzeError.value = safeErrorMessage(err)
    } finally {
      if (id === analyzeSeq) analyzing.value = false
    }
  }

  watch(
    [overrides, enabledCategories, schemaId, stripComments],
    () => {
      if (!hasSource.value) return
      markStale()
      scheduleAnalyze()
    },
    { deep: true },
  )

  watch([consistency, seed, useLlm, llmAlias], () => markStale())

  // -- decisions --------------------------------------------------------

  function decide(key, action, category = null) {
    overrides.value = { ...overrides.value, [key]: { action, category } }
  }

  function decideMany(keys, action, category = null) {
    const next = { ...overrides.value }
    for (const key of keys) next[key] = { action, category }
    overrides.value = next
  }

  function undoDecision(key) {
    const next = { ...overrides.value }
    delete next[key]
    overrides.value = next
  }

  async function remember(item, scope, action, category = null) {
    const rule = buildRule(item, scope, action, category)
    const ok = await rules.addRules([rule])
    if (ok) undoDecision(item.key)
    return ok
  }

  async function rememberMany(items, scope, action, category = null) {
    return rememberDecisions(items.map((item) => ({ item, scope, action, category })))
  }

  async function rememberDecisions(entries) {
    const list = entries.map((entry) =>
      buildRule(entry.item, entry.scope || 'exact', entry.action, entry.category),
    )
    const ok = await rules.addRules(list)
    if (ok) {
      const next = { ...overrides.value }
      for (const entry of entries) delete next[entry.item.key]
      overrides.value = next
    }
    return ok
  }

  function decideEach(entries) {
    const next = { ...overrides.value }
    for (const entry of entries) {
      next[entry.key] = { action: entry.action, category: entry.category ?? null }
    }
    overrides.value = next
  }

  function toggleCategory(id) {
    const set = new Set(enabledCategories.value)
    if (set.has(id)) set.delete(id)
    else set.add(id)
    enabledCategories.value = allCategoryIds.value.filter((c) => set.has(c))
  }

  function setAllCategories(on) {
    enabledCategories.value = on ? [...allCategoryIds.value] : []
  }

  // -- apply ------------------------------------------------------------

  async function apply() {
    applyError.value = ''
    actionMessage.value = ''
    if (!hasSource.value) return
    if (consistency.value === 'project' && !seed.value.trim()) {
      applyError.value = 'Укажите seed проекта или выберите другой режим согласованности'
      return
    }
    applying.value = true
    try {
      const payload = {
        ...buildRequestPayload(currentState()),
        consistency: consistency.value,
        use_llm: Boolean(useLlm.value && llmAvailable.value),
        validate_result: true,
      }
      if (consistency.value === 'project') payload.seed = seed.value.trim()
      if (payload.use_llm && llmAlias.value) payload.llm_alias = llmAlias.value
      result.value = await applyAnonymization(payload)
      resultStale.value = false
      forceHandoff.value = false
      showOriginal.value = false
      return true
    } catch (err) {
      applyError.value = safeErrorMessage(err)
      return false
    } finally {
      applying.value = false
    }
  }

  // -- LLM suggestions --------------------------------------------------

  async function suggestForQueue() {
    const items = queue.value.filter((i) => !llmSuggestions.value[i.key])
    if (!items.length || suggesting.value) return
    suggesting.value = true
    suggestCancelled = false
    suggestError.value = ''
    suggestProgress.value = ''
    try {
      for (let i = 0; i < items.length && !suggestCancelled; i += SUGGEST_PAGE_SIZE) {
        const chunk = items.slice(i, i + SUGGEST_PAGE_SIZE)
        const data = await suggestCategories({
          items: chunk.map((it) => ({
            key: it.key,
            element: it.element,
            attr: it.attr,
            name: it.name || '',
            doc: it.doc || '',
            // Samples from the server are already masked.
            sample: it.samples?.[0] || '',
          })),
          include_samples: true,
          llm_alias: llmAlias.value || undefined,
        })
        const next = { ...llmSuggestions.value }
        for (const [key, category] of Object.entries(data.suggestions || {})) {
          next[key] = category || 'none'
        }
        llmSuggestions.value = next
        if (data.warnings?.length) suggestError.value = data.warnings.join('; ')
      }
    } catch (err) {
      suggestError.value = safeErrorMessage(err)
    } finally {
      suggesting.value = false
    }
  }

  /** Classify the whole DTD in pages; results are cached on the server. */
  async function suggestForSchema() {
    if (!schemaId.value || suggesting.value) return
    suggesting.value = true
    suggestCancelled = false
    suggestError.value = ''
    let done = 0
    try {
      for (let guard = 0; guard < 200 && !suggestCancelled; guard += 1) {
        const data = await suggestCategories({
          schema_id: schemaId.value,
          limit: SUGGEST_PAGE_SIZE,
          llm_alias: llmAlias.value || undefined,
        })
        done += data.processed || 0
        suggestProgress.value = `Классифицировано полей: ${done}` +
          (data.remaining ? `, осталось: ${data.remaining}` : '')
        if (data.warnings?.length) suggestError.value = data.warnings.join('; ')
        if (!data.remaining || !data.processed) break
      }
      suggestProgress.value = `Готово. ${suggestProgress.value}`
      await analyzeNow()
    } catch (err) {
      suggestError.value = safeErrorMessage(err)
    } finally {
      suggesting.value = false
    }
  }

  function cancelSuggest() {
    suggestCancelled = true
  }

  function acceptAiSuggestion(item) {
    const category = item.ai_category
    if (!category) return
    if (category === 'none') decide(item.key, 'keep')
    else decide(item.key, 'replace', category)
  }

  // -- result actions ---------------------------------------------------

  function flash(text) {
    actionMessage.value = text
  }

  function downloadResult() {
    if (!resultXml.value) return
    const blob = new Blob([resultXml.value], { type: 'application/xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = downloadFileName(report.value?.root_element, sourceName.value)
    a.click()
    URL.revokeObjectURL(url)
    flash('Файл скачан')
  }

  async function copyResult() {
    if (!resultXml.value) return
    try {
      await navigator.clipboard.writeText(resultXml.value)
      flash('Скопировано в буфер обмена')
    } catch {
      flash('Не удалось скопировать — выделите текст в редакторе вручную')
    }
  }

  async function saveResultToLibrary({ name, description = '', folder = '' }) {
    if (!resultXml.value) return false
    try {
      await library.saveCurrentDocument({
        name,
        schemaId: schemaId.value,
        xmlText: resultXml.value,
        description: description || 'Анонимизированный документ',
        folder,
      })
      flash(`Сохранено в «Мои документы»: ${name}`)
      return true
    } catch (err) {
      flash(`Не удалось сохранить: ${safeErrorMessage(err)}`)
      return false
    }
  }

  function openInGenerator() {
    if (!resultXml.value) return
    handoff.offerToGenerator(resultXml.value)
    router.push('/')
  }

  // -- bootstrap --------------------------------------------------------

  async function loadSettingsData() {
    const [cats, schemaList, aliases] = await Promise.all([
      getAnonymizeCategories().catch(() => []),
      listSchemas().catch(() => null),
      getConfigAliases().catch(() => null),
    ])
    categories.value = cats
    enabledCategories.value = cats.map((c) => c.id)
    if (schemaList) {
      const list = normalizeDtdListResult(schemaList).schemas
      schemas.value = list
      const primary = pickPrimarySchema(list)
      if (primary && !schemaId.value) schemaId.value = primary.schema_id
    }
    if (aliases) {
      llmAliases.value = aliases.llm || []
      llmAlias.value = aliases.default_llm || llmAliases.value[0] || ''
    }
  }

  onMounted(async () => {
    await Promise.all([loadSettingsData(), rules.load(), library.refreshPersonalDocuments()])
  })

  onBeforeUnmount(() => {
    clearTimeout(analyzeTimer)
    suggestCancelled = true
    sourceXml.value = ''
    result.value = null
  })

  return reactive({
    // source
    sourceXml,
    sourceName,
    sourceError,
    hasSource,
    setSource,
    importFile,
    onSourceEdited,
    clearAll,
    // settings
    schemas,
    schemaId,
    categories,
    enabledCategories,
    stripComments,
    consistency,
    seed,
    useLlm,
    llmAlias,
    llmAliases,
    llmAvailable,
    toggleCategory,
    setAllCategories,
    // analysis
    analysis,
    analyzing,
    analyzeError,
    queue,
    overrides,
    overrideCount,
    analyzeNow,
    decide,
    decideMany,
    decideEach,
    undoDecision,
    remember,
    rememberMany,
    rememberDecisions,
    // result
    result,
    report,
    resultXml,
    status,
    applying,
    applyError,
    resultStale,
    forceHandoff,
    handoffBlocked,
    showOriginal,
    actionMessage,
    apply,
    // llm
    llmSuggestions,
    suggesting,
    suggestProgress,
    suggestError,
    suggestForQueue,
    suggestForSchema,
    cancelSuggest,
    acceptAiSuggestion,
    // result actions
    downloadResult,
    copyResult,
    saveResultToLibrary,
    openInGenerator,
    personalFolders: library.personalFolders,
    // rules
    rules,
  })
}
