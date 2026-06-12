<template>
  <div class="generator" ref="generatorRef">
    <div class="generator-left" :style="{ width: leftWidth + 'px' }">
      <div class="dtd-wrapper card">
        <div class="dtd-collapse-header" @click="dtdCollapsed = !dtdCollapsed">
          <span class="panel-title">DTD Schema</span>
          <span class="collapse-arrow" :class="{ rotated: dtdCollapsed }">▼</span>
        </div>
        <div v-show="!dtdCollapsed">
          <DtdUpload @uploaded="onDtdUploaded" />
        </div>
      </div>

      <div v-if="schemaId" class="card controls">
        <div class="panel-title">Generation</div>

        <div class="field">
          <label>Root Element</label>
          <input
            v-model="rootElement"
            list="root-elements-list"
            placeholder="Element name (type or pick from list)"
            @input="blurAfterDatalistPick"
            @change="blurAfterDatalistPick"
            @keydown.enter="dismissDatalistInput"
            @focus="restoreDatalistPopup"
            @blur="closeDatalistPopup"
          />
          <datalist id="root-elements-list">
            <option v-for="el in elements" :key="el" :value="el" />
          </datalist>
        </div>

        <div class="field">
          <label>Build Mode</label>
          <div class="mode-group">
            <label v-for="m in modes" :key="m.value" class="mode-label">
              <input type="radio" v-model="mode" :value="m.value" />
              {{ m.label }}
            </label>
          </div>
        </div>

        <div v-if="mode === 'maximal'" class="field">
          <label>Repeat Count (+ / *)</label>
          <input v-model.number="repeatCount" type="number" min="1" max="100" />
        </div>

        <DtdTreeView
          v-if="mode === 'custom'"
          ref="dtdTreeRef"
          :schema-id="schemaId"
          :root-element="rootElement"
          @update:paths="customPaths = $event"
          @update:root-element="rootElement = $event"
        />

        <div class="field">
          <label>Populate Strategy</label>
          <select v-model="populateStrategy">
            <option value="faker">Smart Faker (Fast &amp; Local)</option>
            <option value="ai">AI / LLM (Smart Context)</option>
            <option value="hybrid_db_faker">Hybrid: Database + Smart Faker</option>
            <option value="hybrid_db_ai">Hybrid: Database + AI</option>
          </select>
        </div>

        <div v-if="isHybridStrategy" class="db-overrides-panel">
          <div class="overrides-header">
            <div class="overrides-header-top">
              <span class="overrides-title">Database Overrides</span>
              <div class="mapping-preset-actions">
                <input
                  v-model="mappingPresetName"
                  placeholder="Preset name"
                  class="preset-input"
                />
                <button
                  class="btn-secondary"
                  :disabled="!mappingPresetName"
                  @click="saveMappingPreset"
                >
                  Save
                </button>
                <div ref="presetDropdownRef" class="preset-dropdown">
                  <button
                    type="button"
                    class="preset-dropdown-trigger"
                    @click.stop="presetDropdownOpen = !presetDropdownOpen"
                  >
                    {{ presetDropdownLabel }}
                    <span class="preset-dropdown-chevron" :class="{ open: presetDropdownOpen }">▾</span>
                  </button>
                  <div v-if="presetDropdownOpen" class="preset-dropdown-menu" @click.stop>
                    <p v-if="!mappingPresets.length" class="preset-dropdown-empty">
                      No saved presets
                    </p>
                    <label
                      v-for="p in mappingPresets"
                      :key="p.name"
                      class="preset-dropdown-item"
                    >
                      <input
                        v-model="selectedMappingPresetNames"
                        type="checkbox"
                        :value="p.name"
                      />
                      <span class="preset-dropdown-item-label">
                        <span class="preset-dropdown-item-name">{{ p.name }}</span>
                        <span class="preset-meta">
                          {{ p.mapping_count }} mapping{{ p.mapping_count === 1 ? '' : 's' }}
                        </span>
                      </span>
                      <button
                        class="btn-icon-remove"
                        title="Delete preset"
                        @click.prevent="deleteMappingPreset(p.name)"
                      >
                        ×
                      </button>
                    </label>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="selectedMappingPresetNames.length" class="selected-presets-chips">
              <span
                v-for="name in selectedMappingPresetNames"
                :key="name"
                class="preset-chip"
              >
                {{ name }}
                <button
                  class="preset-chip-remove"
                  title="Remove preset"
                  @click="removeSelectedPreset(name)"
                >
                  ×
                </button>
              </span>
            </div>
            <span class="overrides-hint">Stage 1 — DB values fill first, Faker/AI fills the rest</span>
          </div>

          <div v-for="(mapping, mi) in sqlMappings" :key="mi" class="mapping-card">
            <div class="mapping-header">
              <div class="mapping-header-left">
                <span class="mapping-title">Mapping {{ mi + 1 }}</span>
                <span v-if="mapping._presetSource" class="mapping-preset-badge">{{ mapping._presetSource }}</span>
              </div>
              <div class="mapping-header-right">
                <select v-model="mapping.db_alias" class="mapping-db-alias" title="DB alias">
                  <option value="">DB alias...</option>
                  <option v-for="a in dbAliases" :key="a" :value="a">{{ a }}</option>
                </select>
                <button class="btn-icon-remove" @click="removeMapping(mi)" title="Remove mapping">×</button>
              </div>
            </div>

            <div class="field">
              <label>Target Element</label>
              <input
                v-model="mapping.target_element"
                list="target-elements-list"
                placeholder="Element name (type or pick from list)"
                @input="onTargetElementInput(mi, $event)"
                @change="onTargetElementChange(mi, $event)"
                @keydown.enter="dismissDatalistInput"
                @focus="restoreDatalistPopup"
                @blur="closeDatalistPopup"
              />
            </div>

            <div class="field">
              <label>SQL Query</label>
              <textarea
                v-model="mapping.query"
                rows="2"
                placeholder="SELECT col1, col2 FROM schema.view WHERE col = N'value' AND ROWNUM = 1"
              />
            </div>

            <div class="field">
              <label>
                Field Mappings
                <span class="label-hint">DB column → XML attribute</span>
              </label>
              <div v-for="(field, fi) in mapping.fields" :key="fi" class="field-row">
                <input
                  v-model="field.db_col"
                  class="field-input"
                  :list="`db-cols-list-${mi}`"
                  placeholder="DB column (type or pick from list)"
                  @input="blurAfterDatalistPick"
                  @change="blurAfterDatalistPick"
                  @keydown.enter="dismissDatalistInput"
                  @focus="onDbColFocus(mi, $event)"
                  @blur="closeDatalistPopup"
                />
                <span class="field-arrow">→</span>
                <input
                  v-model="field.xml_attr"
                  class="field-input"
                  :list="`xml-attrs-list-${mi}`"
                  placeholder="XML attr (type or pick from list)"
                  @input="blurAfterDatalistPick"
                  @change="blurAfterDatalistPick"
                  @keydown.enter="dismissDatalistInput"
                  @focus="restoreDatalistPopup"
                  @blur="closeDatalistPopup"
                />
                <button
                  class="btn-icon-remove"
                  @click="removeField(mi, fi)"
                  title="Remove field"
                >×</button>
              </div>
              <button class="btn-add-field" @click="addField(mi)">+ Add field</button>
            </div>
          </div>

          <datalist id="target-elements-list">
            <option v-for="el in elements" :key="el" :value="el" />
          </datalist>

          <datalist
            v-for="(mapping, mi) in sqlMappings"
            :id="`xml-attrs-list-${mi}`"
            :key="`xml-attrs-${mi}`"
          >
            <option
              v-for="attr in attributesForTarget(mapping.target_element)"
              :key="attr"
              :value="attr"
            />
          </datalist>

          <datalist
            v-for="(mapping, mi) in sqlMappings"
            :id="`db-cols-list-${mi}`"
            :key="`db-cols-${mi}`"
          >
            <option v-for="col in mappingDbColumns[mi] || []" :key="col" :value="col" />
          </datalist>

          <button class="btn-add-mapping" @click="addMapping">+ Add mapping</button>
        </div>

        <div class="action-row">
          <button class="btn-primary" :disabled="!canGenerate || generating" @click="generate">
            {{ generating ? 'Generating...' : 'Generate XML' }}
          </button>
          <button class="btn-secondary" :disabled="!xmlText || populating" @click="populate">
            {{ populating ? 'Populating...' : 'Populate Data' }}
          </button>
          <button class="btn-secondary" :disabled="!canValidate || validating" @click="validate">
            {{ validating ? 'Validating...' : 'Validate DTD' }}
          </button>
        </div>

        <p v-if="xmlSyncHint" class="error-msg">{{ xmlSyncHint }}</p>
        <p v-if="error" class="error-msg">{{ error }}</p>
        <p v-if="validationResult?.valid" class="validation-msg valid">XML is valid against DTD</p>
        <ul v-else-if="validationResult?.errors?.length" class="validation-errors">
          <li v-for="(err, i) in validationResult.errors" :key="i">
            <span v-if="err.line">Line {{ err.line }}, col {{ err.column }}: </span>{{ err.message }}
          </li>
        </ul>
        <p v-if="buildInfo" class="build-info">
          {{ buildInfo.node_count }} nodes
          <span v-if="buildInfo.warnings?.length"> · {{ buildInfo.warnings.length }} warnings</span>
        </p>
      </div>
    </div>

    <div class="col-divider" @mousedown.prevent="startHResize" title="Drag to resize" />

    <div class="generator-right">
      <XmlEditor
        v-model="xmlText"
        :filename="`${rootElement || 'generated'}.xml`"
        :validation-errors="validationResult?.valid === false ? validationResult.errors : []"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import DtdUpload from '../components/DtdUpload.vue'
import DtdTreeView from '../components/DtdTreeView.vue'
import XmlEditor from '../components/XmlEditor.vue'
import { generateXml } from '../api/generate'
import { populateXml } from '../api/populate'
import { validateXml } from '../api/validate'
import { fetchQueryColumns } from '../api/db'
import { getConfigAliases, listElements } from '../api/dtd'
import {
  listMappingPresets,
  saveMappingPreset as apiSaveMappingPreset,
  loadMappingPreset as apiLoadMappingPreset,
  deleteMappingPreset as apiDeleteMappingPreset,
} from '../api/mappingPresets'
import { extractXmlElementPaths } from '../utils/xmlPaths'

const schemaId = ref('')
const elements = ref([])
const elementAttributes = ref({})
const rootElement = ref('')
const mode = ref('minimal')
const repeatCount = ref(1)
const customPaths = ref([])
const populateStrategy = ref('faker')
const dbAliases = ref([])
const mappingDbColumns = ref({})
const mappingColumnsCache = ref({})
const mappingPresetName = ref('')
const selectedMappingPresetNames = ref([])
const mappingPresets = ref([])
const presetDropdownOpen = ref(false)
const presetDropdownRef = ref(null)

function createEmptyMapping() {
  return {
    target_element: '',
    query: '',
    fields: [{ db_col: '', xml_attr: '' }],
    db_alias: '',
    _presetSource: null,
  }
}
const sqlMappings = ref([createEmptyMapping()])

const isHybridStrategy = computed(
  () => populateStrategy.value === 'hybrid_db_faker' || populateStrategy.value === 'hybrid_db_ai',
)

const presetDropdownLabel = computed(() => {
  const count = selectedMappingPresetNames.value.length
  if (count) return `${count} preset${count === 1 ? '' : 's'} selected`
  const total = mappingPresets.value.length
  if (total) return `Load presets (${total})`
  return 'Load presets...'
})

function addMapping() {
  sqlMappings.value.push(createEmptyMapping())
}

function removeMapping(idx) {
  sqlMappings.value.splice(idx, 1)
  if (sqlMappings.value.length === 0) sqlMappings.value.push(createEmptyMapping())
}

function addField(mi) {
  sqlMappings.value[mi].fields.push({ db_col: '', xml_attr: '' })
}

function removeField(mi, fi) {
  sqlMappings.value[mi].fields.splice(fi, 1)
  if (sqlMappings.value[mi].fields.length === 0)
    sqlMappings.value[mi].fields.push({ db_col: '', xml_attr: '' })
}

function normalizeMappings(mappings, presetSource = null) {
  if (!mappings?.length) return []
  return mappings.map((m) => ({
    target_element: m.target_element || '',
    query: m.query || '',
    fields: m.fields?.length
      ? m.fields.map((f) => ({ db_col: f.db_col || '', xml_attr: f.xml_attr || '' }))
      : [{ db_col: '', xml_attr: '' }],
    db_alias: m.db_alias || '',
    _presetSource: presetSource,
  }))
}

function mappingDbAlias(mapping) {
  return mapping.db_alias
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
}

async function addMappingsFromPreset(name) {
  const preset = await apiLoadMappingPreset(name)
  const newMappings = normalizeMappings(preset.mappings, name)
  sqlMappings.value.push(...newMappings)
  mappingDbColumns.value = {}
}

function removeSelectedPreset(name) {
  selectedMappingPresetNames.value = selectedMappingPresetNames.value.filter((n) => n !== name)
}

async function deleteMappingPreset(name) {
  await apiDeleteMappingPreset(name)
  selectedMappingPresetNames.value = selectedMappingPresetNames.value.filter((n) => n !== name)
  sqlMappings.value = sqlMappings.value.filter((m) => m._presetSource !== name)
  if (sqlMappings.value.length === 0) sqlMappings.value.push(createEmptyMapping())
  await refreshMappingPresets()
}

function onPresetDropdownOutsideClick(event) {
  if (!presetDropdownOpen.value || !presetDropdownRef.value) return
  if (!presetDropdownRef.value.contains(event.target)) {
    presetDropdownOpen.value = false
  }
}

function resetMappingXmlAttrs(mi) {
  for (const field of sqlMappings.value[mi].fields) {
    field.xml_attr = ''
  }
}

function onTargetElementInput(mi, event) {
  blurAfterDatalistPick(event)
  const { inputType } = event
  if (!inputType || inputType === 'insertReplacementText') {
    resetMappingXmlAttrs(mi)
  }
}

function onTargetElementChange(mi, event) {
  resetMappingXmlAttrs(mi)
  blurAfterDatalistPick(event)
}

const allAttributes = computed(() => {
  const names = new Set()
  for (const attrs of Object.values(elementAttributes.value)) {
    for (const attr of attrs) names.add(attr)
  }
  return [...names].sort()
})

function attributesForTarget(targetElement) {
  const attrs = targetElement ? elementAttributes.value[targetElement] : null
  return attrs?.length ? attrs : allAttributes.value
}

function getDatalistOptions(input) {
  const listId = input.dataset.datalistId || input.getAttribute('list')
  if (!listId) return []
  if (listId === 'root-elements-list' || listId === 'target-elements-list') {
    return elements.value
  }
  const attrMatch = listId.match(/^xml-attrs-list-(\d+)$/)
  if (attrMatch) {
    const mapping = sqlMappings.value[Number(attrMatch[1])]
    return mapping ? attributesForTarget(mapping.target_element) : allAttributes.value
  }
  const dbColMatch = listId.match(/^db-cols-list-(\d+)$/)
  if (dbColMatch) {
    return mappingDbColumns.value[Number(dbColMatch[1])] || []
  }
  return []
}

function isDatalistValueSelected(input) {
  const listId = input.dataset.datalistId || input.getAttribute('list')
  const options = getDatalistOptions(input)
  const value = input.value
  if (listId?.startsWith('db-cols-list-')) {
    const lower = value.toLowerCase()
    return options.some((col) => col.toLowerCase() === lower)
  }
  return options.includes(value)
}

async function refreshMappingColumns(mi) {
  const mapping = sqlMappings.value[mi]
  const alias = mappingDbAlias(mapping)
  const query = mapping?.query?.trim()
  if (!alias || !query) {
    mappingDbColumns.value = { ...mappingDbColumns.value, [mi]: [] }
    return
  }

  const cacheKey = `${alias}:${query}`
  if (mappingColumnsCache.value[cacheKey]) {
    mappingDbColumns.value = {
      ...mappingDbColumns.value,
      [mi]: mappingColumnsCache.value[cacheKey],
    }
    return
  }

  try {
    const { columns } = await fetchQueryColumns(alias, query)
    mappingColumnsCache.value[cacheKey] = columns
    mappingDbColumns.value = { ...mappingDbColumns.value, [mi]: columns }
  } catch {
    mappingDbColumns.value = { ...mappingDbColumns.value, [mi]: [] }
  }
}

function onDbColFocus(mi, event) {
  restoreDatalistPopup(event)
  refreshMappingColumns(mi)
}

function restoreDatalistPopup(event) {
  const input = event.target
  const listId = input.dataset.datalistId || input.getAttribute('list')
  if (!listId) return
  input.dataset.datalistId = listId
  input.setAttribute('list', listId)
}

function closeDatalistPopup(event) {
  const input = event.target
  const listId = input.getAttribute('list') || input.dataset.datalistId
  if (!listId) return

  input.dataset.datalistId = listId
  input.removeAttribute('list')
}

function dismissDatalistInput(event) {
  const input = event.target
  closeDatalistPopup(event)
  input.blur()
}

function blurAfterDatalistPick(event) {
  const input = event.target
  const { inputType } = event
  const pickedFromList = event.type === 'change' || !inputType || inputType === 'insertReplacementText'
  if (!pickedFromList) return

  requestAnimationFrame(() => {
    if (!isDatalistValueSelected(input)) return
    closeDatalistPopup(event)
    input.blur()
  })
}

const xmlText = ref('')
const buildInfo = ref(null)
const generating = ref(false)
const populating = ref(false)
const validating = ref(false)
const validationResult = ref(null)
const error = ref('')
const xmlSyncHint = ref('')
const dtdTreeRef = ref(null)

let skipXmlSync = false
let skipModeSync = false
let xmlSyncTimer = null
let columnsFetchTimer = null

const LEFT_MIN = 440
const LEFT_MAX = 700

const leftWidth = ref(LEFT_MIN)
const dtdCollapsed = ref(false)

watch(mode, async (val, oldVal) => {
  if (val === 'custom') {
    dtdCollapsed.value = true
    if (!skipModeSync && oldVal !== 'custom' && xmlText.value?.trim()) {
      await nextTick()
      await applyXmlPathsFromEditor(xmlText.value)
    }
  } else {
    dtdCollapsed.value = false
  }
})

watch(xmlText, (text) => {
  if (skipXmlSync) {
    skipXmlSync = false
    return
  }
  if (!schemaId.value) return

  clearTimeout(xmlSyncTimer)
  xmlSyncTimer = setTimeout(() => {
    syncFromPastedXml(text)
  }, 400)
})

watch(
  sqlMappings,
  () => {
    clearTimeout(columnsFetchTimer)
    columnsFetchTimer = setTimeout(() => {
      sqlMappings.value.forEach((_, mi) => refreshMappingColumns(mi))
    }, 600)
  },
  { deep: true },
)

watch(isHybridStrategy, (enabled) => {
  if (enabled) refreshMappingPresets()
})

watch(selectedMappingPresetNames, async (newNames, oldNames) => {
  const prev = oldNames || []
  const added = newNames.filter((n) => !prev.includes(n))
  const removed = prev.filter((n) => !newNames.includes(n))

  if (removed.length) {
    sqlMappings.value = sqlMappings.value.filter((m) => !removed.includes(m._presetSource))
    mappingDbColumns.value = {}
  }

  for (const name of added) {
    await addMappingsFromPreset(name)
  }

  if (sqlMappings.value.length === 0) {
    sqlMappings.value.push(createEmptyMapping())
  }
})

const modes = [
  { value: 'minimal', label: 'Minimal' },
  { value: 'maximal', label: 'Maximal' },
  { value: 'custom', label: 'Custom' },
]

const canGenerate = computed(() => schemaId.value && rootElement.value)
const canValidate = computed(() => schemaId.value && xmlText.value)

onMounted(async () => {
  document.addEventListener('click', onPresetDropdownOutsideClick)
  try {
    const aliases = await getConfigAliases()
    dbAliases.value = aliases.databases || []
  } catch {
    dbAliases.value = []
  }
  await refreshMappingPresets()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onPresetDropdownOutsideClick)
  clearTimeout(xmlSyncTimer)
  clearTimeout(columnsFetchTimer)
  stopResize()
})

async function onDtdUploaded(result) {
  schemaId.value = result.schema_id
  elements.value = result.elements
  rootElement.value = ''
  selectedMappingPresetNames.value = []
  sqlMappings.value = [createEmptyMapping()]
  await refreshMappingPresets()
  try {
    const summaries = await listElements(result.schema_id)
    elementAttributes.value = Object.fromEntries(summaries.map((s) => [s.name, s.attributes]))
  } catch {
    elementAttributes.value = {}
  }
  skipXmlSync = true
  xmlText.value = ''
  buildInfo.value = null
  validationResult.value = null
  error.value = ''
  xmlSyncHint.value = ''
}

async function applyXmlPathsFromEditor(text) {
  const trimmed = text?.trim()
  if (!trimmed) {
    xmlSyncHint.value = ''
    return
  }

  const parsed = extractXmlElementPaths(trimmed)
  if (!parsed) return

  const { rootTag, elementPaths } = parsed

  if (!rootTag) {
    xmlSyncHint.value = 'XML has no root element — select a root element manually.'
    return
  }

  if (!elements.value.includes(rootTag)) {
    xmlSyncHint.value = `Root element "${rootTag}" is not defined in the DTD schema.`
    return
  }

  xmlSyncHint.value = ''
  await dtdTreeRef.value?.applyXmlElementPaths(elementPaths)
}

async function syncFromPastedXml(text) {
  const trimmed = text?.trim()
  if (!trimmed) {
    xmlSyncHint.value = ''
    return
  }

  const parsed = extractXmlElementPaths(trimmed)
  if (!parsed) return

  const { rootTag } = parsed

  if (!rootTag) {
    xmlSyncHint.value = 'XML has no root element — select a root element manually.'
    return
  }

  if (!elements.value.includes(rootTag)) {
    xmlSyncHint.value = `Root element "${rootTag}" is not defined in the DTD schema.`
    return
  }

  xmlSyncHint.value = ''
  skipModeSync = true
  mode.value = 'custom'
  await nextTick()
  skipModeSync = false
  await applyXmlPathsFromEditor(text)
}

async function generate() {
  generating.value = true
  error.value = ''
  try {
    const config = {
      schema_id: schemaId.value,
      root_element: rootElement.value,
      mode: mode.value,
      repeat_count: repeatCount.value,
      custom_paths: mode.value === 'custom' ? customPaths.value : [],
    }
    const result = await generateXml(config)
    skipXmlSync = true
    xmlText.value = result.xml_text
    buildInfo.value = result
    validationResult.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    generating.value = false
  }
}

async function populate() {
  populating.value = true
  error.value = ''
  try {
    const request = {
      schema_id: schemaId.value,
      xml_text: xmlText.value,
      strategy: populateStrategy.value,
    }
    if (isHybridStrategy.value) {
      request.sql_mappings = sqlMappings.value
        .filter((m) => m.query?.trim() && m.target_element?.trim())
        .map((m) => ({
          query: m.query,
          target_element: m.target_element,
          fields: Object.fromEntries(
            m.fields.filter((f) => f.db_col && f.xml_attr).map((f) => [f.db_col, f.xml_attr]),
          ),
          db_alias: m.db_alias || null,
        }))
    }
    const result = await populateXml(request)
    skipXmlSync = true
    xmlText.value = result.xml_text
    validationResult.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    populating.value = false
  }
}

async function validate() {
  validating.value = true
  error.value = ''
  try {
    validationResult.value = await validateXml(schemaId.value, xmlText.value)
  } catch (e) {
    error.value = e.message
    validationResult.value = null
  } finally {
    validating.value = false
  }
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
  min-width: 440px;
  height: 100%;
  overflow-y: scroll;
}

.dtd-wrapper {
  /* height is controlled inline when Generation panel is present */
}

.dtd-collapse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: 2px 0 8px;
  user-select: none;
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
  gap: 12px;
  margin-top: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mode-group {
  display: flex;
  gap: 12px;
}

.mode-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: var(--text);
  cursor: pointer;
}

.action-row {
  display: flex;
  gap: 8px;
}

.build-info {
  font-size: 12px;
  color: var(--text-muted);
}

.validation-msg.valid {
  font-size: 13px;
  color: var(--success);
}

.validation-errors {
  font-size: 12px;
  color: var(--danger);
  margin-top: 4px;
  padding-left: 18px;
}

.validation-errors li {
  margin-bottom: 4px;
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

/* ── Database Overrides panel ─────────────────────────────────────── */
.db-overrides-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
  background: color-mix(in srgb, var(--border) 20%, transparent);
}

.overrides-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 2px;
}

.overrides-header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.mapping-preset-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.preset-input {
  width: 130px;
}

.preset-dropdown {
  position: relative;
}

.preset-dropdown-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 150px;
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
}

.preset-dropdown-trigger:hover {
  border-color: color-mix(in srgb, var(--border) 60%, var(--text));
}

.preset-dropdown-chevron {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
  transition: transform 0.15s;
}

.preset-dropdown-chevron.open {
  transform: rotate(180deg);
}

.preset-dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 20;
  min-width: 240px;
  max-width: 320px;
  max-height: 220px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--text) 12%, transparent);
}

.preset-dropdown-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 6px 8px;
  margin: 0;
}

.preset-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 4px;
}

.preset-dropdown-item:hover {
  background: color-mix(in srgb, var(--border) 30%, transparent);
}

.preset-dropdown-item input {
  flex-shrink: 0;
}

.preset-dropdown-item-label {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.preset-dropdown-item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preset-meta {
  font-size: 10px;
  color: var(--text-muted);
}

.selected-presets-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.preset-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--border) 35%, transparent);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 2px 8px;
}

.preset-chip-remove {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  padding: 0;
}

.preset-chip-remove:hover {
  color: var(--danger);
}

.mapping-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.mapping-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mapping-preset-badge {
  font-size: 10px;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--border) 40%, transparent);
  border-radius: 3px;
  padding: 1px 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

.mapping-db-alias {
  width: 100px;
  font-size: 11px;
  padding: 2px 4px;
}

.overrides-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.overrides-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.mapping-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 10px;
  background: color-mix(in srgb, var(--border) 10%, transparent);
}

.mapping-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mapping-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.field-input {
  flex: 1;
  min-width: 0;
}

.field-arrow {
  font-size: 13px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.label-hint {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 400;
  margin-left: 4px;
}

.btn-icon-remove {
  background: none;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  padding: 1px 5px;
  transition: color 0.15s, border-color 0.15s;
  flex-shrink: 0;
}

.btn-icon-remove:hover {
  color: var(--danger);
  border-color: var(--danger);
}

.btn-add-field {
  background: none;
  border: 1px dashed var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 3px 8px;
  margin-top: 2px;
  transition: color 0.15s, border-color 0.15s;
  align-self: flex-start;
}

.btn-add-field:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.btn-add-mapping {
  background: none;
  border: 1px dashed var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 5px 10px;
  transition: color 0.15s, border-color 0.15s;
  align-self: flex-start;
}

.btn-add-mapping:hover {
  color: var(--accent);
  border-color: var(--accent);
}
</style>
