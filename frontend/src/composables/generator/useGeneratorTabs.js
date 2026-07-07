import { ref, computed, watch } from 'vue'

const ACTIVE_TAB_KEY = 'xml-gen-left-tab'
const AUTO_VALIDATE_KEY = 'xml-gen-auto-validate'
export const TAB_ORDER = ['structure', 'data', 'results', 'compare', 'library']

export const leftTabs = [
  { id: 'structure', label: 'Структура' },
  { id: 'data', label: 'Данные' },
  { id: 'results', label: 'Результат' },
  { id: 'compare', label: 'Сравнение' },
  { id: 'library', label: 'Библиотека' },
]

function readActiveTab() {
  try {
    const stored = localStorage.getItem(ACTIVE_TAB_KEY)
    if (TAB_ORDER.includes(stored)) return stored
  } catch {
    // ignore storage errors
  }
  return 'structure'
}

function readAutoValidatePreference() {
  try {
    const stored = localStorage.getItem(AUTO_VALIDATE_KEY)
    if (stored === null) return true
    return stored === 'true'
  } catch {
    return true
  }
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
  const autoValidateAfterFill = ref(readAutoValidatePreference())
  let hybridTabSwitched = false

  watch(activeTab, (val) => {
    try {
      localStorage.setItem(ACTIVE_TAB_KEY, val)
    } catch {
      // ignore storage errors
    }
  })

  watch(autoValidateAfterFill, (val) => {
    try {
      localStorage.setItem(AUTO_VALIDATE_KEY, String(val))
    } catch {
      // ignore storage errors
    }
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

  return {
    activeTab,
    autoValidateAfterFill,
    showDataBadge,
    resultsTabBadge,
    resultsTabBadgeLabel,
    onTabKeydown,
    resetHybridTabSwitch,
    focusResultsTab,
    focusStructureTab,
  }
}
