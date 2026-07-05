import { ref, computed, watch, nextTick } from 'vue'
import { fetchQueryPreview } from '../../api/db'
import {
  listMappingPresets,
  saveMappingPreset as apiSaveMappingPreset,
  loadMappingPreset as apiLoadMappingPreset,
  deleteMappingPreset as apiDeleteMappingPreset,
  exportMappingPreset as apiExportMappingPreset,
  parseMappingPresetFile,
} from '../../api/mappingPresets'
import { getMappingValidationIssues } from '../../utils/mappingUtils'

export function useGeneratorMapping({ schemaId, elements, error, isHybridStrategy, fillStrategy }) {
  const dbAliases = ref([])
  const llmAliases = ref([])
  const defaultLlmAlias = ref('')
  const llmAlias = ref('')
  const mappingPresetName = ref('')
  const selectedMappingPresetNames = ref([])
  const mappingPresets = ref([])
  const wizardOpen = ref(false)
  const wizardEditIndex = ref(null)
  const mappingPreview = ref({})
  const suppressPresetMappingSync = ref(false)
  const sqlMappings = ref([])

  let columnsFetchTimer = null

  const usesLlmStrategy = computed(
    () => fillStrategy.value === 'ai' || fillStrategy.value === 'hybrid_db_ai',
  )

  const hasLlmBlocker = computed(
    () => usesLlmStrategy.value && !llmAlias.value,
  )

  const wizardInitialMapping = computed(() =>
    wizardEditIndex.value !== null ? sqlMappings.value[wizardEditIndex.value] : null,
  )

  const presetDropdownLabel = computed(() => {
    const count = selectedMappingPresetNames.value.length
    if (count) return `Выбрано пресетов: ${count}`
    const total = mappingPresets.value.length
    if (total) return `Загрузить пресеты (${total})`
    return 'Загрузить пресеты…'
  })

  const mappingValidation = computed(() =>
    sqlMappings.value.map((mapping, mi) =>
      getMappingValidationIssues(mapping, {
        elements: elements.value,
        preview: mappingPreview.value[mi],
      }),
    ),
  )

  const hasMappingBlockers = computed(() => {
    if (!isHybridStrategy.value) return false
    return sqlMappings.value.some((mapping, mi) => {
      if (!mapping.query?.trim() || !mapping.target_element?.trim()) return false
      return mappingValidation.value[mi]?.errors?.length > 0
    })
  })

  function openMappingWizard(mi = null) {
    wizardEditIndex.value = mi
    wizardOpen.value = true
  }

  function onWizardClose() {
    wizardOpen.value = false
    wizardEditIndex.value = null
  }

  function removeMapping(idx) {
    const mapping = sqlMappings.value[idx]
    const presetSource = mapping?._presetSource

    sqlMappings.value.splice(idx, 1)

    if (!presetSource || !selectedMappingPresetNames.value.includes(presetSource)) return

    suppressPresetMappingSync.value = true
    selectedMappingPresetNames.value = selectedMappingPresetNames.value.filter((n) => n !== presetSource)
    for (const m of sqlMappings.value) {
      if (m._presetSource === presetSource) m._presetSource = null
    }
    nextTick(() => {
      suppressPresetMappingSync.value = false
    })
  }

  function normalizeMappings(mappings, presetSource = null) {
    if (!mappings?.length) return []
    return mappings.map((m) => ({
      target_element: m.target_element || '',
      target_path: m.target_path || '',
      query: m.query || '',
      fields: m.fields?.length
        ? m.fields.map((f) => ({ db_col: f.db_col || '', xml_attr: f.xml_attr || '' }))
        : [{ db_col: '', xml_attr: '' }],
      db_alias: m.db_alias || '',
      _presetSource: presetSource,
    }))
  }

  async function refreshMappingPresets() {
    try {
      mappingPresets.value = await listMappingPresets()
    } catch {
      mappingPresets.value = []
    }
  }

  async function saveMappingPreset() {
    if (!mappingPresetName.value) return
    const mappings = sqlMappings.value.map(({ _presetSource, ...m }) => m)
    await apiSaveMappingPreset({
      name: mappingPresetName.value,
      schema_id: schemaId.value,
      mappings,
    })
    await refreshMappingPresets()
    mappingPresetName.value = ''
  }

  async function addMappingsFromPreset(name) {
    const preset = await apiLoadMappingPreset(name)
    const newMappings = normalizeMappings(preset.mappings, name)
    const startIdx = sqlMappings.value.length
    sqlMappings.value.push(...newMappings)
    for (let mi = startIdx; mi < sqlMappings.value.length; mi += 1) {
      await refreshMappingPreview(mi)
    }
  }

  function removeSelectedPreset(name) {
    selectedMappingPresetNames.value = selectedMappingPresetNames.value.filter((n) => n !== name)
  }

  async function deleteMappingPreset(name) {
    await apiDeleteMappingPreset(name)
    selectedMappingPresetNames.value = selectedMappingPresetNames.value.filter((n) => n !== name)
    sqlMappings.value = sqlMappings.value.filter((m) => m._presetSource !== name)
    await refreshMappingPresets()
  }

  async function exportMappingPreset(name) {
    error.value = ''
    try {
      await apiExportMappingPreset(name)
    } catch (e) {
      error.value = e.message
    }
  }

  async function importMappingPreset(file) {
    error.value = ''
    try {
      const text = await file.text()
      const preset = parseMappingPresetFile(text)
      await apiSaveMappingPreset(preset)
      await refreshMappingPresets()
      if (!selectedMappingPresetNames.value.includes(preset.name)) {
        selectedMappingPresetNames.value = [...selectedMappingPresetNames.value, preset.name]
      }
    } catch (e) {
      error.value = e.message
    }
  }

  async function refreshMappingPreview(mi) {
    const mapping = sqlMappings.value[mi]
    if (!mapping?.db_alias || !mapping?.query?.trim()) {
      const next = { ...mappingPreview.value }
      delete next[mi]
      mappingPreview.value = next
      return
    }
    mappingPreview.value = {
      ...mappingPreview.value,
      [mi]: { loading: true, columns: [], row: undefined, error: '' },
    }
    try {
      const data = await fetchQueryPreview(mapping.db_alias, mapping.query.trim())
      mappingPreview.value = {
        ...mappingPreview.value,
        [mi]: {
          loading: false,
          columns: data.columns || [],
          row: data.row ?? null,
          error: '',
        },
      }
    } catch (e) {
      mappingPreview.value = {
        ...mappingPreview.value,
        [mi]: {
          loading: false,
          columns: [],
          row: undefined,
          error: e.message || 'Ошибка запроса',
        },
      }
    }
  }

  function onWizardFinish(mapping) {
    if (wizardEditIndex.value !== null) {
      const idx = wizardEditIndex.value
      sqlMappings.value[idx] = {
        ...mapping,
        _presetSource: sqlMappings.value[idx]._presetSource,
      }
      refreshMappingPreview(idx)
    } else {
      sqlMappings.value.push(mapping)
      refreshMappingPreview(sqlMappings.value.length - 1)
    }
    onWizardClose()
  }

  function resetMappings() {
    selectedMappingPresetNames.value = []
    sqlMappings.value = []
  }

  watch(
    sqlMappings,
    () => {
      clearTimeout(columnsFetchTimer)
      columnsFetchTimer = setTimeout(() => {
        sqlMappings.value.forEach((m, mi) => {
          if (m.db_alias && m.query?.trim()) refreshMappingPreview(mi)
        })
      }, 600)
    },
    { deep: true },
  )

  watch(isHybridStrategy, (enabled) => {
    if (enabled) refreshMappingPresets()
  })

  watch(selectedMappingPresetNames, async (newNames, oldNames) => {
    if (suppressPresetMappingSync.value) return

    const prev = oldNames || []
    const added = newNames.filter((n) => !prev.includes(n))
    const removed = prev.filter((n) => !newNames.includes(n))

    if (!newNames.length && removed.length) {
      sqlMappings.value = []
      return
    }

    if (removed.length) {
      sqlMappings.value = sqlMappings.value.filter((m) => !removed.includes(m._presetSource))
    }

    for (const name of added) {
      await addMappingsFromPreset(name)
    }
  })

  function dispose() {
    clearTimeout(columnsFetchTimer)
  }

  return {
    dbAliases,
    llmAliases,
    defaultLlmAlias,
    llmAlias,
    mappingPresetName,
    selectedMappingPresetNames,
    mappingPresets,
    wizardOpen,
    wizardInitialMapping,
    mappingPreview,
    sqlMappings,
    presetDropdownLabel,
    mappingValidation,
    hasMappingBlockers,
    hasLlmBlocker,
    usesLlmStrategy,
    openMappingWizard,
    onWizardClose,
    removeMapping,
    saveMappingPreset,
    removeSelectedPreset,
    deleteMappingPreset,
    exportMappingPreset,
    importMappingPreset,
    onWizardFinish,
    refreshMappingPresets,
    resetMappings,
    dispose,
  }
}
