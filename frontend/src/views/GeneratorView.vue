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
            :list="datalistListFor('root', 'root-elements-list')"
            placeholder="Element name (type or pick from list)"
            @focus="openDatalist('root')"
            @blur="scheduleCloseDatalist('root')"
            @change="onRootElementChange"
            @keydown.enter="onDatalistEnter($event, 'root')"
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
          <label>Fill Strategy</label>
          <select v-model="fillStrategy">
            <option value="faker">Smart Faker (Fast &amp; Local)</option>
            <option value="ai">AI / LLM (Smart Context)</option>
            <option value="hybrid_db_faker">Hybrid: Database + Smart Faker</option>
            <option value="hybrid_db_ai">Hybrid: Database + AI</option>
          </select>
        </div>

        <label class="auto-validate-label">
          <input v-model="autoValidateAfterFill" type="checkbox" />
          Auto-validate after Fill
        </label>

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
                <span
                  v-if="mappingPreview[mi] && !mappingPreview[mi].loading && mappingPreview[mi].columns?.length"
                  class="preview-badge"
                  :class="mappingPreview[mi].row === null ? 'warn' : 'ok'"
                >
                  {{ mappingPreview[mi].row === null ? '0 rows' : 'OK' }}
                </span>
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
                :list="datalistListFor(datalistKey('target-el', mi), 'target-elements-list')"
                :readonly="!!mapping.target_path?.trim()"
                placeholder="Element name (type or pick from list)"
                @focus="onTargetElementFocus(mi)"
                @blur="scheduleCloseDatalist(datalistKey('target-el', mi))"
                @change="onTargetElementChange(mi, $event)"
                @keydown.enter="onDatalistEnter($event, datalistKey('target-el', mi))"
              />
            </div>

            <div class="field">
              <label>
                Target Path
                <span class="label-hint">(optional)</span>
              </label>
              <input
                v-model="mapping.target_path"
                :list="pathOptionsForMapping(mapping).length ? `target-paths-list-${mi}` : undefined"
                placeholder="PayDoc.client.contact[0] (optional)"
                @input="onTargetPathInput(mi)"
                @change="onTargetPathChange(mi, $event)"
              />
              <ul
                v-if="pathOptionsForMapping(mapping).length"
                class="path-suggestions"
              >
                <li
                  v-for="p in pathOptionsForMapping(mapping)"
                  :key="p"
                >
                  <button type="button" class="path-suggestion-btn" @click="selectTargetPath(mi, p)">
                    {{ p }}
                  </button>
                </li>
              </ul>
              <p v-else-if="mapping.target_element && xmlText?.trim()" class="path-hint path-hint-muted">
                No matching paths in current XML — type a path manually or generate XML first.
              </p>
              <p class="path-hint">
                Without a path, all &lt;{{ mapping.target_element || 'element' }}&gt; tags in the document will be filled.
                Duplicate siblings use index syntax: <code>contact[0]</code>, <code>contact[1]</code>.
              </p>
            </div>

            <div class="field">
              <label>SQL Query</label>
              <textarea
                v-model="mapping.query"
                rows="2"
                placeholder="SELECT col1, col2 FROM schema.view WHERE col = N'value' AND ROWNUM = 1"
              />
              <div class="query-actions">
                <button
                  class="btn-test-query"
                  :disabled="!mapping.db_alias || !mapping.query?.trim() || mappingPreview[mi]?.loading"
                  @click="testMappingQuery(mi)"
                >
                  {{ mappingPreview[mi]?.loading ? 'Testing...' : 'Test query' }}
                </button>
              </div>
              <p v-if="mappingPreview[mi]?.error" class="mapping-inline-error">
                {{ mappingPreview[mi].error }}
              </p>
              <div
                v-else-if="mappingPreview[mi]?.row"
                class="preview-table-wrap"
              >
                <table class="preview-table">
                  <tbody>
                    <tr v-for="col in mappingPreview[mi].columns" :key="col">
                      <th>{{ col }}</th>
                      <td>{{ formatPreviewValue(mappingPreview[mi].row[col]) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="field">
              <label>
                Field Mappings
                <span class="label-hint">DB column → XML attribute</span>
              </label>
              <div class="field-mapping-actions">
                <button
                  class="btn-add-field"
                  :disabled="!canAutoMap(mi) || autoMapLoading[mi]"
                  @click="autoMapFields(mi)"
                >
                  {{ autoMapLoading[mi] ? 'Mapping...' : 'Auto-map (AI)' }}
                </button>
                <button
                  class="btn-add-field"
                  :disabled="!columnsForMapping(mi).length || autoMapLoading[mi]"
                  @click="addAllColumns(mi)"
                >
                  {{ autoMapLoading[mi] ? 'Mapping...' : 'Add all columns' }}
                </button>
              </div>
              <p v-if="autoMapHint[mi]" class="auto-map-hint">{{ autoMapHint[mi] }}</p>
              <div v-for="(field, fi) in mapping.fields" :key="fi" class="field-row">
                <input
                  v-model="field.db_col"
                  class="field-input"
                  :list="datalistListFor(datalistKey('db-col', mi, fi), `db-cols-list-${mi}`)"
                  placeholder="DB column (type or pick from list)"
                  @focus="onDbColFocus(mi, fi)"
                  @blur="scheduleCloseDatalist(datalistKey('db-col', mi, fi))"
                  @change="onDbColChange(mi, fi, $event)"
                  @keydown.enter="onDatalistEnter($event, datalistKey('db-col', mi, fi))"
                />
                <span class="field-arrow">→</span>
                <input
                  v-model="field.xml_attr"
                  class="field-input"
                  :list="datalistListFor(datalistKey('xml-attr', mi, fi), `xml-attrs-list-${mi}`)"
                  placeholder="XML attr (type or pick from list)"
                  @focus="openDatalist(datalistKey('xml-attr', mi, fi))"
                  @blur="scheduleCloseDatalist(datalistKey('xml-attr', mi, fi))"
                  @change="onXmlAttrChange(mi, fi, $event)"
                  @keydown.enter="onDatalistEnter($event, datalistKey('xml-attr', mi, fi))"
                />
                <button
                  class="btn-icon-remove"
                  @click="removeField(mi, fi)"
                  title="Remove field"
                >×</button>
              </div>
              <button class="btn-add-field" @click="addField(mi)">+ Add field</button>
            </div>

            <ul v-if="mappingValidation[mi]?.errors?.length" class="mapping-errors">
              <li v-for="(err, i) in mappingValidation[mi].errors" :key="'e' + i">{{ err }}</li>
            </ul>
            <ul v-if="mappingValidation[mi]?.warnings?.length" class="mapping-warnings">
              <li v-for="(w, i) in mappingValidation[mi].warnings" :key="'w' + i">{{ w }}</li>
            </ul>
          </div>

          <datalist id="target-elements-list">
            <option v-for="el in elements" :key="el" :value="el" />
          </datalist>

          <datalist
            v-for="(mapping, mi) in sqlMappings"
            :id="`target-paths-list-${mi}`"
            :key="`target-paths-${mi}`"
          >
            <option
              v-for="p in pathOptionsForMapping(mapping)"
              :key="p"
              :value="p"
            />
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

          <div class="mapping-add-row">
            <button class="btn-add-mapping" @click="addMapping">+ Add mapping</button>
            <button class="btn-add-mapping" @click="wizardOpen = true">Add mapping (wizard)</button>
          </div>
        </div>

        <MappingWizard
          :open="wizardOpen"
          :schema-id="schemaId"
          :xml-text="liveXmlText || xmlText"
          :elements="elements"
          :element-attributes="elementAttributes"
          :db-aliases="dbAliases"
          :available-paths="availableElementPaths"
          @close="wizardOpen = false"
          @finish="onWizardFinish"
        />

        <div class="action-row">
          <button class="btn-primary" :disabled="!canGenerate || generating" @click="generate">
            {{ generating ? 'Generating...' : 'Generate XML' }}
          </button>
          <button class="btn-secondary" :disabled="!xmlText || filling || hasMappingBlockers" @click="fill">
            {{ filling ? 'Filling...' : 'Fill Data' }}
          </button>
          <button class="btn-secondary" :disabled="!canValidate || validating" @click="validate">
            {{ validating ? 'Validating...' : 'Validate DTD' }}
          </button>
        </div>

        <div v-if="filling" class="fill-progress" role="status" aria-live="polite">
          <div class="fill-progress-header">
            <span class="fill-spinner" aria-hidden="true" />
            <span class="fill-status">{{ fillStatusMessage }}</span>
            <span class="fill-elapsed">{{ fillElapsedLabel }}</span>
          </div>
          <div class="fill-progress-bar" aria-hidden="true">
            <div class="fill-progress-fill" :style="{ width: fillPercent + '%' }" />
          </div>
        </div>

        <p v-if="xmlSyncHint" class="error-msg">{{ xmlSyncHint }}</p>
        <p v-if="error" class="error-msg">{{ error }}</p>
        <p v-if="validationResult?.valid" class="validation-msg valid">XML is valid against DTD</p>
        <ul v-else-if="validationResult?.errors?.length" class="validation-errors">
          <li v-for="(err, i) in validationResult.errors" :key="i">
            <button
              v-if="err.line"
              type="button"
              class="validation-error-link"
              @click="goToValidationError(err)"
            >
              Line {{ err.line }}, col {{ err.column }}: {{ err.message }}
            </button>
            <span v-else>{{ err.message }}</span>
          </li>
        </ul>
        <p v-if="buildInfo" class="build-info">
          {{ buildInfo.node_count }} nodes
        </p>
        <template v-if="buildInfo?.warnings?.length">
          <p class="build-warnings-heading">
            {{ buildInfo.warnings.length }} warning{{ buildInfo.warnings.length === 1 ? '' : 's' }}:
          </p>
          <ul class="build-warnings">
            <li v-for="(warning, i) in buildInfo.warnings" :key="i">{{ warning }}</li>
          </ul>
        </template>
      </div>
    </div>

    <div class="col-divider" @mousedown.prevent="startHResize" title="Drag to resize" />

    <div class="generator-right">
      <XmlEditor
        ref="xmlEditorRef"
        v-model="xmlText"
        :filename="`${rootElement || 'generated'}.xml`"
        :validation-errors="validationResult?.valid === false ? validationResult.errors : []"
        @content-change="onEditorContentChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import DtdUpload from '../components/DtdUpload.vue'
import DtdTreeView from '../components/DtdTreeView.vue'
import XmlEditor from '../components/XmlEditor.vue'
import MappingWizard from '../components/MappingWizard.vue'
import { generateXml } from '../api/generate'
import { fillXmlStream, suggestFieldMappingsAi } from '../api/fill'
import { validateXml } from '../api/validate'
import { fetchQueryColumns, fetchQueryPreview } from '../api/db'
import { getConfigAliases, listElements, getElementTree } from '../api/dtd'
import {
  listMappingPresets,
  saveMappingPreset as apiSaveMappingPreset,
  loadMappingPreset as apiLoadMappingPreset,
  deleteMappingPreset as apiDeleteMappingPreset,
} from '../api/mappingPresets'
import {
  datalistKey,
  datalistListFor,
  openDatalist,
  scheduleCloseDatalist,
  confirmDatalistPick,
  clearAllDatalistState,
  isOptionSelected,
} from '../utils/datalistInput'
import {
  getMappingValidationIssues,
  lastPathSegment,
  pathsEndingWithTag,
  collectDtdElementPaths,
  buildFieldMappingsFromColumns,
  mappingsToFields,
  normalizeFieldName,
} from '../utils/mappingUtils'

const schemaId = ref('')
const elements = ref([])
const elementAttributes = ref({})
const rootElement = ref('')
const mode = ref('minimal')
const repeatCount = ref(1)
const customPaths = ref([])
const fillStrategy = ref('faker')
const dbAliases = ref([])
const mappingDbColumns = ref({})
const mappingColumnsCache = ref({})
const mappingPresetName = ref('')
const selectedMappingPresetNames = ref([])
const mappingPresets = ref([])
const presetDropdownOpen = ref(false)
const presetDropdownRef = ref(null)
const wizardOpen = ref(false)
const mappingPreview = ref({})
const autoMapLoading = ref({})
const autoMapHint = ref({})
const lastTargetElement = ref({})
const dtdElementPaths = ref([])

function createEmptyMapping() {
  return {
    target_element: '',
    target_path: '',
    query: '',
    fields: [{ db_col: '', xml_attr: '' }],
    db_alias: '',
    _presetSource: null,
  }
}
const sqlMappings = ref([])

const isHybridStrategy = computed(
  () => fillStrategy.value === 'hybrid_db_faker' || fillStrategy.value === 'hybrid_db_ai',
)

const presetDropdownLabel = computed(() => {
  const count = selectedMappingPresetNames.value.length
  if (count) return `${count} preset${count === 1 ? '' : 's'} selected`
  const total = mappingPresets.value.length
  if (total) return `Load presets (${total})`
  return 'Load presets...'
})

function addMapping() {
  const mi = sqlMappings.value.length
  sqlMappings.value.push(createEmptyMapping())
  lastTargetElement.value = { ...lastTargetElement.value, [mi]: '' }
}

function removeMapping(idx) {
  sqlMappings.value.splice(idx, 1)
  const next = {}
  sqlMappings.value.forEach((m, mi) => {
    next[mi] = lastTargetElement.value[mi] ?? m.target_element ?? ''
  })
  lastTargetElement.value = next
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
    target_path: m.target_path || '',
    query: m.query || '',
    fields: m.fields?.length
      ? m.fields.map((f) => ({ db_col: f.db_col || '', xml_attr: f.xml_attr || '' }))
      : [{ db_col: '', xml_attr: '' }],
    db_alias: m.db_alias || '',
    _presetSource: presetSource,
  }))
}

function syncLastTargetElements() {
  const next = { ...lastTargetElement.value }
  sqlMappings.value.forEach((m, mi) => {
    if (next[mi] === undefined) next[mi] = m.target_element || ''
  })
  lastTargetElement.value = next
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
  mappingPresetName.value = ''
}

async function addMappingsFromPreset(name) {
  const preset = await apiLoadMappingPreset(name)
  const newMappings = normalizeMappings(preset.mappings, name)
  sqlMappings.value.push(...newMappings)
  mappingDbColumns.value = {}
  syncLastTargetElements()
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

function onDatalistEnter(event, key) {
  confirmDatalistPick(key)
  event.target.blur()
}

function onRootElementChange(event) {
  const input = event.target
  if (!input.value || isOptionSelected(input, elements.value)) {
    confirmDatalistPick('root')
  }
}

function onTargetElementFocus(mi) {
  if (sqlMappings.value[mi]?.target_path?.trim()) return
  openDatalist(datalistKey('target-el', mi))
}

function onTargetElementChange(mi, event) {
  const input = event.target
  const value = input.value.trim()
  const prev = lastTargetElement.value[mi] ?? ''

  if (value !== prev) {
    resetMappingXmlAttrs(mi)
    lastTargetElement.value = { ...lastTargetElement.value, [mi]: value }
  }

  if (!value || isOptionSelected(input, elements.value)) {
    confirmDatalistPick(datalistKey('target-el', mi))
  }
}

function onTargetPathInput(mi) {
  const mapping = sqlMappings.value[mi]
  const seg = lastPathSegment(mapping.target_path)
  if (!seg || seg === mapping.target_element) return

  mapping.target_element = seg
  const prev = lastTargetElement.value[mi] ?? ''
  if (seg !== prev) {
    resetMappingXmlAttrs(mi)
    lastTargetElement.value = { ...lastTargetElement.value, [mi]: seg }
  }
}

function onTargetPathChange(mi, event) {
  onTargetPathInput(mi)
  const input = event.target
  const paths = pathOptionsForMapping(sqlMappings.value[mi])
  if (!input.value || paths.includes(input.value)) {
    return
  }
}

function selectTargetPath(mi, path) {
  sqlMappings.value[mi].target_path = path
  onTargetPathInput(mi)
}

function pathOptionsForMapping(mapping) {
  return pathsEndingWithTag(availableElementPaths.value, mapping.target_element)
}

const availableElementPaths = computed(() => {
  const text = (liveXmlText.value || xmlText.value || '').trim()
  const parsed = extractXmlElementPaths(text)
  if (parsed?.elementPaths?.length) return parsed.elementPaths
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

function formatPreviewValue(val) {
  if (val === null || val === undefined) return '—'
  return String(val)
}

function columnsForMapping(mi) {
  return mappingPreview.value[mi]?.columns || mappingDbColumns.value[mi] || []
}

function canAutoMap(mi) {
  const mapping = sqlMappings.value[mi]
  return (
    columnsForMapping(mi).length > 0
    && mapping.target_element?.trim()
    && attributesForTarget(mapping.target_element).length > 0
  )
}

async function testMappingQuery(mi) {
  const mapping = sqlMappings.value[mi]
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
    if (data.columns?.length) {
      mappingDbColumns.value = { ...mappingDbColumns.value, [mi]: data.columns }
      const current = sqlMappings.value[mi]
      if (current.target_element?.trim() && schemaId.value) {
        autoMapLoading.value = { ...autoMapLoading.value, [mi]: true }
        try {
          const result = await suggestMappingsForCard(mi, { keepFilled: true })
          if (result) {
            sqlMappings.value[mi] = { ...current, fields: result.fields }
            autoMapHint.value = { ...autoMapHint.value, [mi]: result.hint }
          }
        } finally {
          autoMapLoading.value = { ...autoMapLoading.value, [mi]: false }
        }
      }
    }
  } catch (e) {
    mappingPreview.value = {
      ...mappingPreview.value,
      [mi]: {
        loading: false,
        columns: [],
        row: undefined,
        error: e.message || 'Query failed',
      },
    }
  }
}

async function suggestMappingsForCard(mi, { keepFilled = true } = {}) {
  const mapping = sqlMappings.value[mi]
  const columns = columnsForMapping(mi)
  if (!columns.length || !schemaId.value || !mapping.target_element?.trim()) {
    return null
  }

  const columnKeys = new Set(columns.map((c) => normalizeFieldName(c)))
  const filled = keepFilled
    ? mapping.fields.filter(
        (f) =>
          f.db_col?.trim()
          && f.xml_attr?.trim()
          && columnKeys.has(normalizeFieldName(f.db_col)),
      )
    : []

  try {
    const { mappings, matcher } = await suggestFieldMappingsAi({
      schemaId: schemaId.value,
      targetElement: mapping.target_element,
      columns,
      existingMappings: filled.map((f) => ({
        db_col: f.db_col,
        xml_attr: f.xml_attr,
      })),
    })
    return {
      fields: mappingsToFields(mappings),
      matcher,
      hint: matcher === 'llm'
        ? 'Matched via AI using DTD attribute docs.'
        : 'LLM unavailable — used local fuzzy matching.',
    }
  } catch (e) {
    return {
      fields: buildFieldMappingsFromColumns(
        columns,
        attributesForTarget(mapping.target_element),
        filled,
      ),
      matcher: 'fuzzy',
      hint: `AI mapping failed (${e.message}) — used local fuzzy matching.`,
    }
  }
}

async function autoMapFields(mi) {
  autoMapLoading.value = { ...autoMapLoading.value, [mi]: true }
  autoMapHint.value = { ...autoMapHint.value, [mi]: '' }
  try {
    const result = await suggestMappingsForCard(mi, { keepFilled: true })
    if (!result) return
    sqlMappings.value[mi] = {
      ...sqlMappings.value[mi],
      fields: result.fields,
    }
    autoMapHint.value = { ...autoMapHint.value, [mi]: result.hint }
  } finally {
    autoMapLoading.value = { ...autoMapLoading.value, [mi]: false }
  }
}

async function addAllColumns(mi) {
  autoMapLoading.value = { ...autoMapLoading.value, [mi]: true }
  autoMapHint.value = { ...autoMapHint.value, [mi]: '' }
  try {
    const result = await suggestMappingsForCard(mi, { keepFilled: false })
    if (!result) return
    sqlMappings.value[mi] = {
      ...sqlMappings.value[mi],
      fields: result.fields,
    }
    autoMapHint.value = { ...autoMapHint.value, [mi]: result.hint }
  } finally {
    autoMapLoading.value = { ...autoMapLoading.value, [mi]: false }
  }
}

function onWizardFinish(mapping) {
  sqlMappings.value.push(mapping)
  wizardOpen.value = false
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

function onDbColFocus(mi, fi) {
  openDatalist(datalistKey('db-col', mi, fi))
  refreshMappingColumns(mi)
}

function onDbColChange(mi, fi, event) {
  const cols = mappingDbColumns.value[mi] || []
  const input = event.target
  if (!input.value || isOptionSelected(input, cols, { caseInsensitive: true })) {
    confirmDatalistPick(datalistKey('db-col', mi, fi))
  }
}

function onXmlAttrChange(mi, fi, event) {
  const mapping = sqlMappings.value[mi]
  const attrs = attributesForTarget(mapping.target_element)
  const input = event.target
  if (!input.value || isOptionSelected(input, attrs)) {
    confirmDatalistPick(datalistKey('xml-attr', mi, fi))
  }
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

const xmlText = ref('')
const liveXmlText = ref('')
const buildInfo = ref(null)
const generating = ref(false)
const filling = ref(false)
const fillStatusMessage = ref('')
const fillPercent = ref(0)
const fillElapsedSeconds = ref(0)
const validating = ref(false)
const validationResult = ref(null)

const AUTO_VALIDATE_KEY = 'xml-gen-auto-validate'

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
const dtdTreeRef = ref(null)
const xmlEditorRef = ref(null)

function goToValidationError(err) {
  if (!err?.line) return
  xmlEditorRef.value?.goToPosition(err.line, err.column)
}

function getEditorXmlText() {
  return xmlEditorRef.value?.getValue?.() ?? xmlText.value
}

function scheduleXmlSync(text, delay = 150) {
  if (!schemaId.value) return
  clearTimeout(xmlSyncTimer)
  const snapshot = text ?? getEditorXmlText()
  xmlSyncTimer = setTimeout(() => {
    syncFromPastedXml(snapshot || getEditorXmlText())
  }, delay)
}

function onEditorContentChange(text) {
  liveXmlText.value = text || ''
  if (ignoreNextXmlWatch) {
    ignoreNextXmlWatch = false
    clearTimeout(xmlSyncTimer)
    return
  }
  scheduleXmlSync(text)
}

async function waitForDtdTreeRef(maxAttempts = 5) {
  for (let i = 0; i < maxAttempts; i += 1) {
    if (dtdTreeRef.value) return dtdTreeRef.value
    await nextTick()
  }
  return dtdTreeRef.value
}

let ignoreNextXmlWatch = false
let skipModeSync = false
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

const LEFT_MIN = 440
const LEFT_MAX = 700

const leftWidth = ref(LEFT_MIN)
const dtdCollapsed = ref(false)

watch(mode, async (val, oldVal) => {
  if (val === 'custom') {
    dtdCollapsed.value = true
    if (!skipModeSync && oldVal !== 'custom' && getEditorXmlText()?.trim()) {
      await nextTick()
      await applyXmlPathsFromEditor(getEditorXmlText())
    }
  } else {
    dtdCollapsed.value = false
  }
})

watch(
  sqlMappings,
  () => {
    syncLastTargetElements()
    clearTimeout(columnsFetchTimer)
    columnsFetchTimer = setTimeout(() => {
      sqlMappings.value.forEach((_, mi) => refreshMappingColumns(mi))
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

watch([schemaId, rootElement], () => {
  refreshDtdElementPaths()
})

watch(selectedMappingPresetNames, async (newNames, oldNames) => {
  const prev = oldNames || []
  const added = newNames.filter((n) => !prev.includes(n))
  const removed = prev.filter((n) => !newNames.includes(n))

  if (!newNames.length && removed.length) {
    sqlMappings.value = []
    mappingDbColumns.value = {}
    return
  }

  if (removed.length) {
    sqlMappings.value = sqlMappings.value.filter((m) => !removed.includes(m._presetSource))
    mappingDbColumns.value = {}
  }

  for (const name of added) {
    await addMappingsFromPreset(name)
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
  stopFillProgressTimer()
  stopResize()
  clearAllDatalistState()
})

async function onDtdUploaded(result) {
  schemaId.value = result.schema_id
  elements.value = result.elements
  rootElement.value = ''
  selectedMappingPresetNames.value = []
  sqlMappings.value = []
  await refreshMappingPresets()
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

  await nextTick()
  const editorXml = getEditorXmlText()?.trim()
  if (editorXml) {
    if (xmlText.value !== editorXml) {
      ignoreNextXmlWatch = true
      xmlText.value = editorXml
    }
    await syncFromPastedXml(editorXml)
    return
  }

  ignoreNextXmlWatch = true
  xmlText.value = ''
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
  if (rootTag && rootElement.value !== rootTag) {
    rootElement.value = rootTag
    await nextTick()
  }
  await waitForDtdTreeRef()
  await dtdTreeRef.value?.applyXmlElementPaths(elementPaths)
  await nextTick()
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
  await waitForDtdTreeRef()
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
    ignoreNextXmlWatch = true
    xmlText.value = result.xml_text
    liveXmlText.value = result.xml_text
    buildInfo.value = result
    validationResult.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    generating.value = false
  }
}

async function fill() {
  filling.value = true
  error.value = ''
  resetFillProgress()
  fillStatusMessage.value = 'Starting fill...'
  startFillProgressTimer()
  let filled = false
  try {
    const request = {
      schema_id: schemaId.value,
      xml_text: xmlText.value,
      strategy: fillStrategy.value,
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
    const result = await fillXmlStream(request, ({ message, percent }) => {
      if (message) fillStatusMessage.value = message
      if (typeof percent === 'number') fillPercent.value = percent
    })
    ignoreNextXmlWatch = true
    xmlText.value = result.xml_text
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
  }
}

async function runValidation() {
  if (!schemaId.value || !xmlText.value) return

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

.auto-validate-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: fit-content;
  margin-bottom: 0;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  white-space: nowrap;
}

.auto-validate-label input[type="checkbox"] {
  width: 14px;
  height: 14px;
  min-width: 14px;
  padding: 0;
  margin: 0;
  flex-shrink: 0;
  accent-color: var(--accent);
}

.action-row {
  display: flex;
  gap: 8px;
}

.fill-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}

.fill-progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.fill-spinner {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  border: 2px solid color-mix(in srgb, var(--accent) 20%, var(--border));
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: fill-spin 0.75s linear infinite;
}

@keyframes fill-spin {
  to { transform: rotate(360deg); }
}

.fill-status {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text);
}

.fill-elapsed {
  flex-shrink: 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

.fill-progress-bar {
  height: 4px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 15%, var(--border));
  overflow: hidden;
}

.fill-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
  transition: width 0.35s ease;
}

.build-info {
  font-size: 12px;
  color: var(--text-muted);
}

.build-warnings-heading {
  font-size: 12px;
  color: var(--warning);
  margin-top: 4px;
}

.build-warnings {
  font-size: 12px;
  color: var(--warning);
  margin-top: 2px;
  padding-left: 18px;
}

.build-warnings li {
  margin-bottom: 4px;
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

.validation-error-link {
  display: inline;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.validation-error-link:hover {
  opacity: 0.85;
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
  width: 260px;
  max-height: 220px;
  overflow-x: hidden;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px;
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
  width: 100%;
  min-width: 0;
  margin-bottom: 0;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 4px;
}

.preset-dropdown-item:hover {
  background: color-mix(in srgb, var(--border) 30%, transparent);
}

.preset-dropdown-item input[type="checkbox"] {
  width: 14px;
  height: 14px;
  min-width: 14px;
  padding: 0;
  margin: 0;
  flex: 0 0 14px;
  accent-color: var(--accent);
}

.preset-dropdown-item-label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.preset-dropdown-item-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

.preset-dropdown-item .btn-icon-remove {
  flex: 0 0 auto;
  padding: 0 4px;
  font-size: 14px;
  line-height: 1.2;
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

.mapping-add-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.path-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
}

.path-hint-muted {
  font-style: italic;
}

.path-suggestions {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  max-height: 120px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
}

.path-suggestions li {
  margin: 0;
}

.path-suggestion-btn {
  display: block;
  width: 100%;
  text-align: left;
  padding: 4px 8px;
  border: none;
  background: none;
  font-size: 11px;
  font-family: monospace;
  color: var(--text);
  cursor: pointer;
}

.path-suggestion-btn:hover {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--accent);
}

.query-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.btn-test-query {
  background: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 3px 10px;
  transition: color 0.15s, border-color 0.15s;
}

.btn-test-query:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}

.btn-test-query:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mapping-inline-error {
  font-size: 12px;
  color: var(--danger);
  margin: 4px 0 0;
}

.field-mapping-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 4px;
}

.auto-map-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0 0 4px;
}

.preview-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 8px;
}

.preview-badge.ok {
  color: var(--success);
  background: color-mix(in srgb, var(--success) 15%, transparent);
}

.preview-badge.warn {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 15%, transparent);
}

.preview-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
  margin-top: 4px;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.preview-table th,
.preview-table td {
  padding: 3px 6px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.preview-table th {
  color: var(--text-muted);
  font-weight: 500;
  white-space: nowrap;
}

.mapping-errors {
  font-size: 12px;
  color: var(--danger);
  margin: 0;
  padding-left: 18px;
}

.mapping-warnings {
  font-size: 12px;
  color: var(--warning);
  margin: 0;
  padding-left: 18px;
}
</style>
