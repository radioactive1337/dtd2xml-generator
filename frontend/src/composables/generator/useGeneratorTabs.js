import { ref, computed, watch } from 'vue'

const ACTIVE_TAB_KEY = 'xml-gen-left-tab'
const AUTO_VALIDATE_KEY = 'xml-gen-auto-validate'
const PRESERVE_FILLED_KEY = 'xml-gen-preserve-filled'
export const TAB_ORDER = ['structure', 'data', 'results', 'compare', 'library']

export const leftTabs = [
  { id: 'structure', label: 'Структура' },
  { id: 'data', label: 'Данные' },
  { id: 'results', label: 'Результат' },
  { id: 'compare', label: 'Сравнение' },
  { id: 'library', label: 'Библиотека' },
]

function readBoolPreference(key, defaultValue) {
  try {
    const stored = localStorage.getItem(key)
    if (stored === null) return defaultValue
    return stored === 'true'
  } catch {
    return defaultValue
  }
}

function writeBoolPreference(key, value) {
  try {
    localStorage.setItem(key, String(value))
  } catch {
    // ignore storage errors
  }
}

function readActiveTab() {
  try {
    const stored = localStorage.getItem(ACTIVE_TAB_KEY)
    if (TAB_ORDER.includes(stored)) return stored
  } catch {
    // ignore storage errors
  }
  return 'structure'
}

export function useGeneratorTabs({
  hasMappingBlockers,
  hasLlmBlocker,
  isHybridStrategy,
  sqlMappings,
  validationResult,
  buildInfo,
  xmlSyncHint,
  fillStrategy,
}) {
  const activeTab = ref(readActiveTab())
  const autoValidateAfterFill = ref(readBoolPreference(AUTO_VALIDATE_KEY, true))
  const preserveFilled = ref(readBoolPreference(PRESERVE_FILLED_KEY, true))
  let hybridTabSwitched = false

  watch(activeTab, (val) => {
    try {
      localStorage.setItem(ACTIVE_TAB_KEY, val)
    } catch {
      // ignore storage errors
    }
  })

  watch(autoValidateAfterFill, (val) => {
    writeBoolPreference(AUTO_VALIDATE_KEY, val)
  })

  watch(preserveFilled, (val) => {
    writeBoolPreference(PRESERVE_FILLED_KEY, val)
  })

  watch(fillStrategy, (val) => {
    if ((val === 'hybrid_db_faker' || val === 'hybrid_db_ai') && !hybridTabSwitched) {
      activeTab.value = 'data'
      hybridTabSwitched = true
    }
  })

  const showDataBadge = computed(() => {
    if (hasMappingBlockers.value) return true
    if (hasLlmBlocker.value) return true
    if (isHybridStrategy.value && !sqlMappings.value.length) return true
    return false
  })

  const dataTabBadgeLabel = computed(() => {
    if (hasMappingBlockers.value) return 'Ошибки в SQL-маппингах'
    if (hasLlmBlocker.value) return 'Не выбран LLM-алиас'
    if (isHybridStrategy.value && !sqlMappings.value.length) return 'Нет SQL-маппингов для гибридной стратегии'
    return ''
  })

  const resultsTabBadge = computed(() => {
    if (validationResult.value?.valid === false && validationResult.value?.errors?.length) return 'error'
    if (validationResult.value?.valid === true) return 'ok'
    if (xmlSyncHint.value) return 'error'
    if (buildInfo.value?.warnings?.length) return 'warn'
    if (buildInfo.value && !buildInfo.value.warnings?.length) return 'ok'
    return null
  })

  const resultsTabBadgeLabel = computed(() => {
    if (resultsTabBadge.value === 'error') return 'Есть ошибки'
    if (resultsTabBadge.value === 'warn') return 'Есть предупреждения'
    if (resultsTabBadge.value === 'ok') return 'Всё в порядке'
    return ''
  })

  function onTabKeydown(event, tabId) {
    const idx = TAB_ORDER.indexOf(tabId)
    if (idx < 0) return
    if (event.key === 'ArrowLeft' && idx > 0) {
      event.preventDefault()
      activeTab.value = TAB_ORDER[idx - 1]
    } else if (event.key === 'ArrowRight' && idx < TAB_ORDER.length - 1) {
      event.preventDefault()
      activeTab.value = TAB_ORDER[idx + 1]
    }
  }

  function resetHybridTabSwitch() {
    hybridTabSwitched = false
  }

  function focusResultsTab() {
    activeTab.value = 'results'
  }

  function focusStructureTab() {
    activeTab.value = 'structure'
  }

  function focusCompareTab() {
    activeTab.value = 'compare'
  }

  return {
    activeTab,
    autoValidateAfterFill,
    preserveFilled,
    showDataBadge,
    dataTabBadgeLabel,
    resultsTabBadge,
    resultsTabBadgeLabel,
    onTabKeydown,
    resetHybridTabSwitch,
    focusResultsTab,
    focusStructureTab,
    focusCompareTab,
  }
}
