<template>
  <div class="generator" ref="generatorRef">
    <div class="generator-left" :style="{ width: leftWidth + 'px' }">
      <div class="dtd-wrapper card">
        <div class="dtd-collapse-header" @click="dtdCollapsed = !dtdCollapsed">
          <div class="dtd-header-main">
            <span class="panel-title">Схема DTD</span>
            <span v-if="schemaId && dtdCollapsed" class="dtd-header-status">
              ✓ {{ dtdMeta.fileName }} · {{ elementCountLabel }}
            </span>
          </div>
          <span class="collapse-arrow" :class="{ rotated: dtdCollapsed }">▼</span>
        </div>
        <div v-show="!dtdCollapsed">
          <DtdUpload
            :is-loaded="!!schemaId"
            :file-name="dtdMeta.fileName"
            :element-count="dtdMeta.elementCount"
            @uploaded="onDtdUploaded"
          />
        </div>
      </div>

      <nav
        v-if="schemaId"
        class="left-tabs-bar"
        role="tablist"
        aria-label="Панели генерации"
      >
        <button
          v-for="tab in leftTabs"
          :id="`left-tab-${tab.id}`"
          :key="tab.id"
          type="button"
          role="tab"
          class="left-tab-btn"
          :class="{ active: activeTab === tab.id }"
          :aria-selected="activeTab === tab.id"
          :tabindex="activeTab === tab.id ? 0 : -1"
          @click="activeTab = tab.id"
          @keydown="onTabKeydown($event, tab.id)"
        >
          {{ tab.label }}
          <span
            v-if="tab.id === 'data' && showDataBadge"
            class="left-tab-badge left-tab-badge--warn"
            aria-label="Требует внимания"
          />
          <span
            v-if="tab.id === 'results' && resultsTabBadge"
            class="left-tab-badge"
            :class="`left-tab-badge--${resultsTabBadge}`"
            :aria-label="resultsTabBadgeLabel"
          />
        </button>
      </nav>

      <div v-if="schemaId" class="card controls left-panel-body">
        <div
          class="left-tab-content"
          role="tabpanel"
          :aria-labelledby="`left-tab-${activeTab}`"
        >
          <GeneratorStructureTab
            v-show="activeTab === 'structure'"
            ref="structureTabRef"
            :schema-id="schemaId"
            :elements="elements"
            v-model:root-element="rootElement"
            v-model:mode="mode"
            v-model:repeat-count="repeatCount"
            v-model:custom-paths="customPaths"
          />

          <GeneratorDataTab
            v-show="activeTab === 'data'"
            v-model:fill-strategy="fillStrategy"
            v-model:llm-alias="llmAlias"
            :llm-aliases="llmAliases"
            :default-llm-alias="defaultLlmAlias"
            v-model:auto-validate-after-fill="autoValidateAfterFill"
            v-model:mapping-preset-name="mappingPresetName"
            v-model:selected-mapping-preset-names="selectedMappingPresetNames"
            :is-hybrid-strategy="isHybridStrategy"
            :mapping-presets="mappingPresets"
            :preset-dropdown-label="presetDropdownLabel"
            :sql-mappings="sqlMappings"
            :mapping-preview="mappingPreview"
            :mapping-validation="mappingValidation"
            @save-mapping-preset="saveMappingPreset"
            @import-mapping-preset="importMappingPreset"
            @export-mapping-preset="exportMappingPreset"
            @open-mapping-wizard="openMappingWizard"
            @remove-mapping="removeMapping"
            @delete-mapping-preset="deleteMappingPreset"
            @remove-selected-preset="removeSelectedPreset"
          />

          <GeneratorResultsTab
            v-show="activeTab === 'results'"
            :validation-result="validationResult"
            :build-info="buildInfo"
            :xml-sync-hint="xmlSyncHint"
            :history="generationHistory"
            :max-entries="historyMaxEntries"
            @go-to-error="goToValidationError"
            @restore="restoreFromHistory"
            @remove="removeHistoryEntry"
            @clear-history="clearGenerationHistory"
          />
        </div>

        <GeneratorActionFooter
          :can-generate="canGenerate"
          :generating="generating"
          :xml-text="xmlText"
          :filling="filling"
          :has-mapping-blockers="hasMappingBlockers || hasLlmBlocker"
          :can-validate="canValidate"
          :validating="validating"
          :fill-status-message="fillStatusMessage"
          :fill-percent="fillPercent"
          :fill-elapsed-label="fillElapsedLabel"
          :error="error"
          @generate="generate"
          @fill="fill"
          @validate="validate"
        />
      </div>

      <MappingWizard
        :open="wizardOpen"
        :initial-mapping="wizardInitialMapping"
        :schema-id="schemaId"
        :xml-text="liveXmlText || xmlText"
        :elements="elements"
        :element-attributes="elementAttributes"
        :db-aliases="dbAliases"
        :llm-alias="llmAlias"
        :available-paths="availableElementPaths"
        @close="onWizardClose"
        @finish="onWizardFinish"
      />
    </div>

    <div class="col-divider" @mousedown.prevent="startHResize" title="Потяните для изменения ширины" />

    <div class="generator-right">
      <XmlEditor
        ref="xmlEditorRef"
        :model-value="xmlText"
        :filename="`${rootElement || 'generated'}.xml`"
        :validation-errors="validationResult?.valid === false ? validationResult.errors : []"
        @content-change="onEditorContentChange"
        @import="onXmlFileImported"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import DtdUpload from '../components/DtdUpload.vue'
import XmlEditor from '../components/XmlEditor.vue'
import MappingWizard from '../components/MappingWizard.vue'
import GeneratorStructureTab from '../components/generator/GeneratorStructureTab.vue'
import GeneratorDataTab from '../components/generator/GeneratorDataTab.vue'
import GeneratorResultsTab from '../components/generator/GeneratorResultsTab.vue'
import GeneratorActionFooter from '../components/generator/GeneratorActionFooter.vue'
import { useGenerationHistory } from '../composables/useGenerationHistory'
import { generateXml } from '../api/generate'
import { fillXmlStream, stageFillXml } from '../api/fill'
import { validateXml } from '../api/validate'
import { fetchQueryPreview } from '../api/db'
import { getConfigAliases } from '../api/config'
import { listElements, getElementTree, listSchemas } from '../api/dtd'
import {
  listMappingPresets,
  saveMappingPreset as apiSaveMappingPreset,
  loadMappingPreset as apiLoadMappingPreset,
  deleteMappingPreset as apiDeleteMappingPreset,
  exportMappingPreset as apiExportMappingPreset,
  parseMappingPresetFile,
} from '../api/mappingPresets'
import { clearAllDatalistState } from '../utils/datalistInput'
import {
  getMappingValidationIssues,
  collectDtdElementPaths,
} from '../utils/mappingUtils'
import { pickPrimarySchema, schemaFileName } from '../utils/dtdSchema'
import { extractXmlElementPaths } from '../utils/xmlPaths'
import { formatElements } from '../utils/ruPlural'
import { translateFillStep } from '../utils/fillProgress'

const schemaId = ref('')
const dtdMeta = ref({ fileName: '', elementCount: 0 })
const elements = ref([])
const elementAttributes = ref({})
const rootElement = ref('')
const mode = ref('minimal')
const repeatCount = ref(1)
const customPaths = ref([])
const fillStrategy = ref('faker')
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
const dtdElementPaths = ref([])

const sqlMappings = ref([])

const isHybridStrategy = computed(
  () => fillStrategy.value === 'hybrid_db_faker' || fillStrategy.value === 'hybrid_db_ai',
)

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

const elementCountLabel = computed(() => formatElements(dtdMeta.value.elementCount))

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

const availableElementPaths = computed(() => {
  const text = (liveXmlText.value || xmlText.value || '').trim()
  if (!text) return dtdElementPaths.value
  try {
    // skipFormat: during live editing XML is often partial/malformed; the
    // xml-formatter fallback never repairs structural invalidity, only whitespace.
    const parsed = extractXmlElementPaths(text, { skipFormat: true })
    if (parsed?.elementPaths?.length) return parsed.elementPaths
  } catch {
    // malformed or partial XML in editor
  }
  return dtdElementPaths.value
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

const xmlText = ref('')
const xmlDirty = ref(false)
const liveXmlText = ref('')
const buildInfo = ref(null)
const generating = ref(false)
const filling = ref(false)
const fillStatusMessage = ref('')
const fillPercent = ref(0)
const fillElapsedSeconds = ref(0)
const validating = ref(false)
const validationResult = ref(null)

const {
  history: generationHistory,
  addEntry: addHistoryEntry,
  removeEntry: removeHistoryEntry,
  clearHistory: clearGenerationHistory,
  maxEntries: historyMaxEntries,
} = useGenerationHistory()

const AUTO_VALIDATE_KEY = 'xml-gen-auto-validate'
const ACTIVE_TAB_KEY = 'xml-gen-left-tab'
const TAB_ORDER = ['structure', 'data', 'results']

function readActiveTab() {
  try {
    const stored = localStorage.getItem(ACTIVE_TAB_KEY)
    if (TAB_ORDER.includes(stored)) return stored
  } catch {
    // ignore storage errors
  }
  return 'structure'
}

const activeTab = ref(readActiveTab())
let hybridTabSwitched = false

const leftTabs = [
  { id: 'structure', label: 'Структура' },
  { id: 'data', label: 'Данные' },
  { id: 'results', label: 'Результат' },
]

watch(activeTab, (val) => {
  try {
    localStorage.setItem(ACTIVE_TAB_KEY, val)
  } catch {
    // ignore storage errors
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

function readAutoValidatePreference() {
  try {
    const stored = localStorage.getItem(AUTO_VALIDATE_KEY)
    if (stored === null) return true
    return stored === 'true'
  } catch {
    return true
  }
}

const autoValidateAfterFill = ref(readAutoValidatePreference())

watch(autoValidateAfterFill, (val) => {
  try {
    localStorage.setItem(AUTO_VALIDATE_KEY, String(val))
  } catch {
    // ignore storage errors
  }
})

const error = ref('')
const xmlSyncHint = ref('')
const structureTabRef = ref(null)
const xmlEditorRef = ref(null)

function goToValidationError(err) {
  if (!err?.line) return
  xmlEditorRef.value?.goToPosition(err.line, err.column)
}

function getEditorXmlText() {
  return xmlEditorRef.value?.getValue?.() ?? xmlText.value
}

async function setProgrammaticXml(text, { dirty = false } = {}) {
  clearTimeout(xmlSyncTimer)
  xmlSyncTimer = null
  ignoreNextXmlWatch = true
  const xml = text || ''
  liveXmlText.value = xml
  xmlText.value = xml
  xmlDirty.value = dirty
  await nextTick()
  xmlEditorRef.value?.setValue?.(xml)
  ignoreNextXmlWatch = false
}

function scheduleXmlSync(text, delay = 150) {
  if (!schemaId.value || generating.value || filling.value || ignoreNextXmlWatch) return
  clearTimeout(xmlSyncTimer)
  const snapshot = text ?? getEditorXmlText()
  xmlSyncTimer = setTimeout(() => {
    if (generating.value || filling.value || ignoreNextXmlWatch) return
    syncFromPastedXml(snapshot || getEditorXmlText())
  }, delay)
}

function onEditorContentChange(text) {
  if (ignoreNextXmlWatch || generating.value || filling.value) return
  liveXmlText.value = text || ''
  xmlText.value = text || ''
  xmlDirty.value = true
  scheduleXmlSync(text)
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

let ignoreNextXmlWatch = false
let skipModeSync = false
let generateRequestSeq = 0
let xmlSyncTimer = null
let columnsFetchTimer = null
let fillElapsedTimer = null

const fillElapsedLabel = computed(() => {
  const seconds = fillElapsedSeconds.value
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}m ${remainder}s`
})

function startFillProgressTimer() {
  fillElapsedSeconds.value = 0
  clearInterval(fillElapsedTimer)
  fillElapsedTimer = setInterval(() => {
    fillElapsedSeconds.value += 1
  }, 1000)
}

function stopFillProgressTimer() {
  clearInterval(fillElapsedTimer)
  fillElapsedTimer = null
}

function resetFillProgress() {
  fillStatusMessage.value = ''
  fillPercent.value = 0
  fillElapsedSeconds.value = 0
}

const LEFT_PANEL_WIDTH_KEY = 'xml-gen-left-panel-width'
const LEFT_MIN = 480
const LEFT_MAX = 960

function readLeftPanelWidth() {
  try {
    const stored = parseInt(localStorage.getItem(LEFT_PANEL_WIDTH_KEY), 10)
    if (!Number.isNaN(stored)) {
      return Math.max(LEFT_MIN, Math.min(LEFT_MAX, stored))
    }
  } catch {
    // ignore storage errors
  }
  return LEFT_MIN
}

const leftWidth = ref(readLeftPanelWidth())

watch(leftWidth, (val) => {
  try {
    localStorage.setItem(LEFT_PANEL_WIDTH_KEY, String(val))
  } catch {
    // ignore storage errors
  }
})
const dtdCollapsed = ref(false)

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

watch(wizardOpen, async (isOpen) => {
  if (isOpen) {
    await nextTick()
    liveXmlText.value = getEditorXmlText() || xmlText.value || ''
  }
})

watch(isHybridStrategy, (enabled) => {
  if (enabled) refreshMappingPresets()
})

watch(fillStrategy, (val) => {
  if ((val === 'hybrid_db_faker' || val === 'hybrid_db_ai') && !hybridTabSwitched) {
    activeTab.value = 'data'
    hybridTabSwitched = true
  }
})

watch([schemaId, rootElement], () => {
  refreshDtdElementPaths()
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

const canGenerate = computed(() => schemaId.value && rootElement.value)
const canValidate = computed(() => schemaId.value && xmlText.value)

async function restoreSavedSchema() {
  try {
    const schemas = await listSchemas()
    const primary = pickPrimarySchema(schemas)
    if (primary) await onDtdUploaded(primary)
  } catch {
    // No saved schemas or API unavailable — user can upload manually.
  }
}

onMounted(async () => {
  await restoreSavedSchema()
  try {
    const aliases = await getConfigAliases()
    dbAliases.value = aliases.databases || []
    llmAliases.value = aliases.llm || []
    defaultLlmAlias.value = aliases.default_llm || ''
    llmAlias.value = defaultLlmAlias.value || llmAliases.value[0] || ''
  } catch {
    dbAliases.value = []
    llmAliases.value = []
    defaultLlmAlias.value = ''
    llmAlias.value = ''
  }
})

onBeforeUnmount(() => {
  clearTimeout(xmlSyncTimer)
  clearTimeout(columnsFetchTimer)
  stopFillProgressTimer()
  stopResize()
  clearAllDatalistState()
})

async function onDtdUploaded(result) {
  schemaId.value = result.schema_id
  dtdMeta.value = {
    fileName: schemaFileName(result),
    elementCount: result.element_count,
  }
  elements.value = result.elements
  rootElement.value = ''
  selectedMappingPresetNames.value = []
  sqlMappings.value = []
  if (isHybridStrategy.value) await refreshMappingPresets()
  try {
    const summaries = await listElements(result.schema_id)
    elementAttributes.value = Object.fromEntries(summaries.map((s) => [s.name, s.attributes]))
  } catch {
    elementAttributes.value = {}
  }
  buildInfo.value = null
  validationResult.value = null
  error.value = ''
  xmlSyncHint.value = ''
  dtdCollapsed.value = true
  activeTab.value = 'structure'
  hybridTabSwitched = false

  await nextTick()
  const editorXml = getEditorXmlText()?.trim()
  if (editorXml) {
    await setProgrammaticXml(editorXml)
    await syncFromPastedXml(editorXml)
    return
  }

  await setProgrammaticXml('')
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

    if (!rootTag) {
      xmlSyncHint.value = 'В XML нет корневого элемента — выберите корень вручную'
      return
    }

    if (!elements.value.includes(rootTag)) {
      xmlSyncHint.value = `Корневой элемент «${rootTag}» не описан в DTD`
      return
    }

    xmlSyncHint.value = ''
    if (rootTag && rootElement.value !== rootTag) {
      rootElement.value = rootTag
      await nextTick()
    }
    const treeRef = await waitForDtdTreeRef()
    await treeRef?.applyXmlElementPaths(elementPaths)
    await nextTick()
    await treeRef?.applyXmlElementPaths(elementPaths)
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

    if (!rootTag) {
      xmlSyncHint.value = 'В XML нет корневого элемента — выберите корень вручную'
      return
    }

    if (!elements.value.includes(rootTag)) {
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

async function restoreFromHistory(entry) {
  if (!entry?.xml_text) return
  validationResult.value =
    entry.validation_valid === true ? { valid: true, errors: [] } : null
  buildInfo.value =
    entry.node_count != null
      ? { node_count: entry.node_count, warnings: entry.warnings || [] }
      : null
  xmlSyncHint.value = ''
  error.value = ''
  await setProgrammaticXml(entry.xml_text, { dirty: true })
}

async function generate() {
  const requestSeq = ++generateRequestSeq
  generating.value = true
  error.value = ''
  clearTimeout(xmlSyncTimer)
  xmlSyncTimer = null
  try {
    const config = {
      schema_id: schemaId.value,
      root_element: rootElement.value,
      mode: mode.value,
      repeat_count: repeatCount.value,
      custom_paths: mode.value === 'custom' ? customPaths.value : [],
    }
    const result = await generateXml(config)
    if (requestSeq !== generateRequestSeq) return
    await setProgrammaticXml(result.xml_text)
    buildInfo.value = result
    validationResult.value = null
    addHistoryEntry({
      type: 'generate',
      schema_id: schemaId.value,
      root_element: rootElement.value,
      mode: mode.value,
      xml_text: result.xml_text,
      node_count: result.node_count,
      warnings: result.warnings || [],
    })
    // In custom mode the tree drives generation; syncing back from XML
    // mis-resolves CHOICE branches that share element names (e.g. employer).
    if (result.warnings?.length) {
      activeTab.value = 'results'
    }
  } catch (e) {
    if (requestSeq === generateRequestSeq) error.value = e.message
  } finally {
    if (requestSeq === generateRequestSeq) generating.value = false
  }
}

async function fill() {
  filling.value = true
  error.value = ''
  resetFillProgress()
  fillStatusMessage.value = 'Запуск заполнения…'
  startFillProgressTimer()
  let filled = false
  try {
    if (xmlDirty.value) {
      fillStatusMessage.value = 'Загрузка XML…'
      await stageFillXml(schemaId.value, getEditorXmlText() || xmlText.value)
      xmlDirty.value = false
    }

    const request = {
      schema_id: schemaId.value,
      strategy: fillStrategy.value,
    }
    if (llmAlias.value) {
      request.llm_alias = llmAlias.value
    }
    if (isHybridStrategy.value) {
      request.sql_mappings = sqlMappings.value
        .filter((m) => m.query?.trim() && m.target_element?.trim())
        .map((m) => ({
          query: m.query,
          target_element: m.target_element,
          target_path: m.target_path?.trim() || null,
          fields: Object.fromEntries(
            m.fields.filter((f) => f.db_col && f.xml_attr).map((f) => [f.db_col, f.xml_attr]),
          ),
          db_alias: m.db_alias || null,
        }))
    }
    const result = await fillXmlStream(request, ({ step, message, percent }) => {
      const translated = translateFillStep(step)
      if (translated) fillStatusMessage.value = translated
      else if (message) fillStatusMessage.value = message
      if (typeof percent === 'number') fillPercent.value = percent
    })
    await setProgrammaticXml(result.xml_text)
    xmlDirty.value = false
    filled = true
  } catch (e) {
    error.value = e.message
  } finally {
    stopFillProgressTimer()
    filling.value = false
  }
  if (filled) {
    if (autoValidateAfterFill.value) {
      await runValidation()
    } else {
      validationResult.value = null
    }
    addHistoryEntry({
      type: 'fill',
      schema_id: schemaId.value,
      root_element: rootElement.value,
      xml_text: xmlText.value,
      node_count: buildInfo.value?.node_count ?? null,
      warnings: buildInfo.value?.warnings || [],
      validation_valid: validationResult.value?.valid ?? null,
    })
  }
}

async function runValidation() {
  if (!schemaId.value || !xmlText.value) return

  validating.value = true
  error.value = ''
  try {
    validationResult.value = await validateXml(schemaId.value, getEditorXmlText() || xmlText.value)
    if (validationResult.value?.valid === true) {
      xmlSyncHint.value = ''
    } else if (validationResult.value?.valid === false) {
      activeTab.value = 'results'
    }
  } catch (e) {
    error.value = e.message
    validationResult.value = null
  } finally {
    validating.value = false
  }
}

async function validate() {
  await runValidation()
}

// ---- Resize logic ----
let activeResize = null
let resizeStartX = 0
let resizeStartVal = 0

function startHResize(e) {
  activeResize = 'h'
  resizeStartX = e.clientX
  resizeStartVal = leftWidth.value
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onResizeMove(e) {
  if (activeResize === 'h') {
    const delta = e.clientX - resizeStartX
    leftWidth.value = Math.max(LEFT_MIN, Math.min(LEFT_MAX, resizeStartVal + delta))
  }
}

function stopResize() {
  activeResize = null
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
</script>

<style scoped>
.generator {
  display: flex;
  align-items: stretch;
  gap: 0;
  height: 100%;
  flex: 1;
  min-height: 0;
}

.generator-left {
  display: flex;
  flex-direction: column;
  gap: 0;
  flex-shrink: 0;
  min-width: 480px;
  height: 100%;
  overflow: hidden;
}

.dtd-wrapper {
  flex-shrink: 0;
}

.left-tabs-bar {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  padding: 8px 12px 0;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}

.left-tab-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  background: none;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.left-tab-btn:hover {
  color: var(--text);
}

.left-tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.left-tab-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 4px 4px 0 0;
}

.left-tab-badge {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.left-tab-badge--warn {
  background: var(--warning);
}

.left-tab-badge--error {
  background: var(--danger);
}

.left-tab-badge--ok {
  background: var(--success);
}

.left-panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin-top: 0;
  container-type: inline-size;
}

.left-tab-content {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.dtd-collapse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: 2px 0 8px;
  user-select: none;
}

.dtd-header-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.dtd-header-status {
  font-size: 12px;
  color: var(--success);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dtd-collapse-header:hover .panel-title {
  color: var(--text);
}

.dtd-collapse-header .panel-title {
  margin-bottom: 0;
  transition: color 0.15s;
}

.collapse-arrow {
  font-size: 11px;
  color: var(--text-muted);
  transition: transform 0.2s ease, color 0.15s;
}

.collapse-arrow.rotated {
  transform: rotate(-90deg);
}


.col-divider {
  width: 8px;
  align-self: stretch;
  cursor: col-resize;
  position: relative;
  flex-shrink: 0;
}

.col-divider::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  transform: translateX(-50%);
  background: var(--border);
  border-radius: 2px;
  transition: background 0.15s;
}

.col-divider:hover::after {
  background: var(--accent);
}

.generator-right {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.controls {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-top: 0;
}

@media (max-width: 900px) {
  .generator {
    flex-direction: column;
  }
  .generator-left {
    width: 100% !important;
  }
  .col-divider {
    display: none;
  }
}
</style>

