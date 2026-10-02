import { ref, computed } from 'vue'
import {
  clearAnonymizeRules,
  deleteAnonymizeRule,
  deleteGlobalAnonymizeRule,
  exportAnonymizeRules,
  getAnonymizeRules,
  importAnonymizeRules,
  promoteAnonymizeRule,
  upsertAnonymizeRules,
} from '../api/anonymize'
import { filterRules, safeErrorMessage } from '../utils/anonymize'

/** Global (read-only) and personal anonymization rules. */
export function useAnonymizeRules({ onChanged } = {}) {
  const globalRules = ref([])
  const userRules = ref([])
  const loading = ref(false)
  const error = ref('')
  const message = ref('')
  const query = ref('')
  const layerFilter = ref('all')
  const sourceFilter = ref('')

  const visibleRules = computed(() => {
    const filter = { query: query.value, source: sourceFilter.value }
    const rows = []
    if (layerFilter.value !== 'user') {
      rows.push(...filterRules(globalRules.value, filter).map((r) => ({ ...r, layer: 'global' })))
    }
    if (layerFilter.value !== 'global') {
      rows.push(...filterRules(userRules.value, filter).map((r) => ({ ...r, layer: 'user' })))
    }
    return rows
  })

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const data = await getAnonymizeRules()
      globalRules.value = data.global || []
      userRules.value = data.user || []
    } catch (err) {
      error.value = safeErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function changed() {
    if (onChanged) await onChanged()
  }

  async function addRules(rules, { successMessage = '' } = {}) {
    error.value = ''
    try {
      const data = await upsertAnonymizeRules(rules)
      userRules.value = data.user || []
      await changed()
      if (successMessage) message.value = successMessage
      return true
    } catch (err) {
      error.value = safeErrorMessage(err)
      message.value = ''
      return false
    }
  }

  async function promote(ruleId) {
    error.value = ''
    message.value = ''
    try {
      const data = await promoteAnonymizeRule(ruleId)
      globalRules.value = data.global || []
      userRules.value = data.user || []
      message.value = 'Правило перенесено в общие'
      await changed()
      return true
    } catch (err) {
      error.value = safeErrorMessage(err)
      return false
    }
  }

  async function remove(ruleId) {
    error.value = ''
    try {
      await deleteAnonymizeRule(ruleId)
      userRules.value = userRules.value.filter((r) => r.id !== ruleId)
      await changed()
    } catch (err) {
      error.value = safeErrorMessage(err)
    }
  }

  async function removeGlobal(ruleId) {
    error.value = ''
    message.value = ''
    try {
      const data = await deleteGlobalAnonymizeRule(ruleId)
      globalRules.value = data.global || []
      message.value = 'Общее правило удалено'
      await changed()
    } catch (err) {
      error.value = safeErrorMessage(err)
    }
  }

  async function clearUser() {
    error.value = ''
    try {
      await clearAnonymizeRules()
      userRules.value = []
      await changed()
    } catch (err) {
      error.value = safeErrorMessage(err)
    }
  }

  async function exportJson(layer = 'user') {
    error.value = ''
    try {
      const data = await exportAnonymizeRules(layer)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'anonymize_rules.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      error.value = safeErrorMessage(err)
    }
  }

  async function importFile(file, mode = 'merge') {
    error.value = ''
    message.value = ''
    try {
      const parsed = JSON.parse(await file.text())
      const rules = Array.isArray(parsed) ? parsed : parsed?.rules
      if (!Array.isArray(rules)) {
        error.value = 'В файле нет списка rules'
        return
      }
      const data = await importAnonymizeRules(rules, mode)
      userRules.value = data.user || []
      message.value =
        `Импортировано: ${data.imported}` + (data.skipped ? `, пропущено некорректных: ${data.skipped}` : '')
      await changed()
    } catch (err) {
      error.value = err instanceof SyntaxError ? 'Файл не является корректным JSON' : safeErrorMessage(err)
    }
  }

  return {
    globalRules,
    userRules,
    loading,
    error,
    message,
    query,
    layerFilter,
    sourceFilter,
    visibleRules,
    load,
    addRules,
    promote,
    remove,
    removeGlobal,
    clearUser,
    exportJson,
    importFile,
  }
}
