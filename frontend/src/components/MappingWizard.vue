<template>
  <div v-if="open" class="wizard-overlay" @click.self="close">
    <div class="wizard-dialog" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
      <div class="wizard-header">
        <h3 id="wizard-title">Add Mapping (Wizard)</h3>
        <button class="btn-icon-remove" title="Close" @click="close">×</button>
      </div>

      <div class="wizard-steps">
        <button
          v-for="(label, i) in stepLabels"
          :key="label"
          type="button"
          class="wizard-step"
          :class="{ active: step === i, done: step > i }"
          @click="step = i"
        >
          {{ i + 1 }}. {{ label }}
        </button>
      </div>

      <div class="wizard-body">
        <!-- Step 0: Element -->
        <div v-if="step === 0" class="wizard-panel">
          <label>Target Element</label>
          <input
            v-model="draft.target_element"
            list="wizard-elements-list"
            placeholder="Search or type element name"
            @input="onElementChange"
          />
          <datalist id="wizard-elements-list">
            <option v-for="el in filteredElements" :key="el" :value="el" />
          </datalist>
          <p class="wizard-hint">Pick the XML element whose attributes will be filled from SQL.</p>
        </div>

        <!-- Step 1: Optional path -->
        <div v-if="step === 1" class="wizard-panel">
          <label>Target Path <span class="label-hint">(optional)</span></label>
          <input
            v-model="draft.target_path"
            list="wizard-paths-list"
            placeholder="PayDoc.Body.client (optional)"
            @input="onPathChange"
          />
          <datalist id="wizard-paths-list">
            <option v-for="p in pathOptions" :key="p" :value="p" />
          </datalist>
          <p class="wizard-hint">
            Without a path, all &lt;{{ draft.target_element || 'element' }}&gt; tags in the document will be filled.
          </p>
        </div>

        <!-- Step 2: SQL -->
        <div v-if="step === 2" class="wizard-panel">
          <div class="wizard-row">
            <label>DB Alias</label>
            <select v-model="draft.db_alias">
              <option value="">Select alias...</option>
              <option v-for="a in dbAliases" :key="a" :value="a">{{ a }}</option>
            </select>
          </div>
          <label>SQL Query</label>
          <textarea
            v-model="draft.query"
            rows="4"
            placeholder="SELECT col1, col2 FROM schema.view WHERE ROWNUM = 1"
          />
          <div class="wizard-row">
            <button
              class="btn-secondary"
              :disabled="!canTestQuery || preview.loading"
              @click="testQuery"
            >
              {{ preview.loading ? 'Testing...' : 'Test query' }}
            </button>
            <span v-if="previewBadge" class="preview-badge" :class="previewBadge.kind">
              {{ previewBadge.text }}
            </span>
          </div>
          <p v-if="preview.error" class="wizard-error">{{ preview.error }}</p>
          <div v-if="preview.row" class="preview-table-wrap">
            <table class="preview-table">
              <tbody>
                <tr v-for="col in preview.columns" :key="col">
                  <th>{{ col }}</th>
                  <td>{{ formatPreviewValue(preview.row[col]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Step 3: Fields -->
        <div v-if="step === 3" class="wizard-panel">
          <div class="wizard-row">
            <button
              class="btn-secondary"
              :disabled="!canAutoMap || autoMapLoading"
              @click="autoMap"
            >
              {{ autoMapLoading ? 'Mapping...' : 'Auto-map (AI)' }}
            </button>
            <button
              class="btn-secondary"
              :disabled="!preview.columns?.length || autoMapLoading"
              @click="addAllColumns"
            >
              {{ autoMapLoading ? 'Mapping...' : 'Add all columns' }}
            </button>
          </div>
          <p v-if="autoMapHint" class="wizard-hint">{{ autoMapHint }}</p>
          <div v-for="(field, fi) in draft.fields" :key="fi" class="field-row">
            <input
              v-model="field.db_col"
              class="field-input"
              placeholder="DB column"
            />
            <span class="field-arrow">→</span>
            <input
              v-model="field.xml_attr"
              class="field-input"
              :list="'wizard-attrs-list'"
              placeholder="XML attr"
            />
            <button class="btn-icon-remove" title="Remove" @click="removeField(fi)">×</button>
          </div>
          <datalist id="wizard-attrs-list">
            <option v-for="attr in xmlAttrs" :key="attr" :value="attr" />
          </datalist>
          <button class="btn-add-field" @click="addField">+ Add field</button>
        </div>

        <!-- Step 4: Review -->
        <div v-if="step === 4" class="wizard-panel">
          <dl class="review-list">
            <dt>Element</dt>
            <dd>{{ draft.target_element || '—' }}</dd>
            <dt>Path</dt>
            <dd>{{ draft.target_path || '(all matching tags)' }}</dd>
            <dt>DB Alias</dt>
            <dd>{{ draft.db_alias || '—' }}</dd>
            <dt>Query</dt>
            <dd class="review-query">{{ draft.query || '—' }}</dd>
            <dt>Fields</dt>
            <dd>
              <ul v-if="filledFields.length" class="review-fields">
                <li v-for="f in filledFields" :key="f.db_col + f.xml_attr">
                  {{ f.db_col }} → {{ f.xml_attr }}
                </li>
              </ul>
              <span v-else>—</span>
            </dd>
          </dl>
          <ul v-if="validation.errors.length" class="mapping-errors">
            <li v-for="(err, i) in validation.errors" :key="'e' + i">{{ err }}</li>
          </ul>
          <ul v-if="validation.warnings.length" class="mapping-warnings">
            <li v-for="(w, i) in validation.warnings" :key="'w' + i">{{ w }}</li>
          </ul>
        </div>
      </div>

      <div class="wizard-footer">
        <button class="btn-secondary" :disabled="step === 0" @click="step -= 1">Back</button>
        <button v-if="step < 4" class="btn-primary" :disabled="!canAdvance" @click="step += 1">
          Next
        </button>
        <button v-else class="btn-primary" :disabled="validation.errors.length" @click="finish">
          Add mapping
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { fetchQueryPreview } from '../api/db'
import { suggestFieldMappingsAi } from '../api/fill'
import {
  getMappingValidationIssues,
  lastPathSegment,
  pathsEndingWithTag,
  buildFieldMappingsFromColumns,
  mappingsToFields,
  normalizeFieldName,
} from '../utils/mappingUtils'

const props = defineProps({
  open: { type: Boolean, default: false },
  schemaId: { type: String, default: '' },
  elements: { type: Array, default: () => [] },
  elementAttributes: { type: Object, default: () => ({}) },
  dbAliases: { type: Array, default: () => [] },
  availablePaths: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'finish'])

const stepLabels = ['Element', 'Path', 'SQL', 'Fields', 'Review']
const step = ref(0)
const elementFilter = ref('')

const draft = ref(createEmptyDraft())
const preview = ref({ loading: false, columns: [], row: undefined, error: '' })
const autoMapLoading = ref(false)
const autoMapHint = ref('')

function createEmptyDraft() {
  return {
    target_element: '',
    target_path: '',
    query: '',
    fields: [{ db_col: '', xml_attr: '' }],
    db_alias: '',
  }
}

const filteredElements = computed(() => {
  const q = elementFilter.value.toLowerCase()
  if (!q) return props.elements
  return props.elements.filter((el) => el.toLowerCase().includes(q))
})

const pathOptions = computed(() =>
  pathsEndingWithTag(props.availablePaths, draft.value.target_element),
)

const xmlAttrs = computed(() => {
  const el = draft.value.target_element
  const attrs = el ? props.elementAttributes[el] : null
  return attrs?.length ? attrs : []
})

const filledFields = computed(() =>
  draft.value.fields.filter((f) => f.db_col && f.xml_attr),
)

const canTestQuery = computed(
  () => draft.value.db_alias?.trim() && draft.value.query?.trim(),
)

const canAutoMap = computed(
  () => preview.value.columns?.length && draft.value.target_element && xmlAttrs.value.length,
)

const previewBadge = computed(() => {
  if (preview.value.loading) return null
  if (preview.value.error) return { kind: 'error', text: 'Error' }
  if (!preview.value.columns?.length && !preview.value.error) return null
  if (preview.value.row === null) return { kind: 'warn', text: '0 rows' }
  if (preview.value.row) return { kind: 'ok', text: 'OK' }
  return null
})

const validation = computed(() =>
  getMappingValidationIssues(draft.value, {
    elements: props.elements,
    preview: preview.value,
  }),
)

const canAdvance = computed(() => {
  if (step.value === 0) return !!draft.value.target_element?.trim()
  if (step.value === 2) return !!draft.value.query?.trim() && !!draft.value.db_alias?.trim()
  return true
})

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      step.value = 0
      draft.value = createEmptyDraft()
      preview.value = { loading: false, columns: [], row: undefined, error: '' }
      autoMapHint.value = ''
      elementFilter.value = ''
    }
  },
)

function onElementChange(event) {
  elementFilter.value = event.target.value
  if (draft.value.target_path) {
    const seg = lastPathSegment(draft.value.target_path)
    if (seg !== draft.value.target_element) {
      draft.value.target_path = ''
    }
  }
}

function onPathChange() {
  const seg = lastPathSegment(draft.value.target_path)
  if (seg) draft.value.target_element = seg
}

function formatPreviewValue(val) {
  if (val === null || val === undefined) return '—'
  return String(val)
}

async function suggestDraftMappings({ keepFilled = true } = {}) {
  const columns = preview.value.columns || []
  if (!columns.length || !props.schemaId || !draft.value.target_element?.trim()) {
    return null
  }

  const columnKeys = new Set(columns.map((c) => normalizeFieldName(c)))
  const filled = keepFilled
    ? draft.value.fields.filter(
        (f) =>
          f.db_col?.trim()
          && f.xml_attr?.trim()
          && columnKeys.has(normalizeFieldName(f.db_col)),
      )
    : []

  try {
    const { mappings, matcher } = await suggestFieldMappingsAi({
      schemaId: props.schemaId,
      targetElement: draft.value.target_element,
      columns,
      existingMappings: filled.map((f) => ({
        db_col: f.db_col,
        xml_attr: f.xml_attr,
      })),
    })
    return {
      fields: mappingsToFields(mappings),
      hint: matcher === 'llm'
        ? 'Matched via AI using DTD attribute docs.'
        : 'LLM unavailable — used local fuzzy matching.',
    }
  } catch (e) {
    return {
      fields: buildFieldMappingsFromColumns(columns, xmlAttrs.value, filled),
      hint: `AI mapping failed (${e.message}) — used local fuzzy matching.`,
    }
  }
}

async function testQuery() {
  preview.value = { loading: true, columns: [], row: undefined, error: '' }
  try {
    const data = await fetchQueryPreview(draft.value.db_alias, draft.value.query.trim())
    preview.value = {
      loading: false,
      columns: data.columns || [],
      row: data.row ?? null,
      error: '',
    }
    if (data.columns?.length && draft.value.target_element) {
      autoMapLoading.value = true
      try {
        const result = await suggestDraftMappings({ keepFilled: true })
        if (result) {
          draft.value.fields = result.fields
          autoMapHint.value = result.hint
        }
      } finally {
        autoMapLoading.value = false
      }
    }
  } catch (e) {
    preview.value = {
      loading: false,
      columns: [],
      row: undefined,
      error: e.message || 'Query failed',
    }
  }
}

async function autoMap() {
  autoMapLoading.value = true
  autoMapHint.value = ''
  try {
    const result = await suggestDraftMappings({ keepFilled: true })
    if (result) {
      draft.value.fields = result.fields
      autoMapHint.value = result.hint
    }
  } finally {
    autoMapLoading.value = false
  }
}

async function addAllColumns() {
  autoMapLoading.value = true
  autoMapHint.value = ''
  try {
    const result = await suggestDraftMappings({ keepFilled: false })
    if (result) {
      draft.value.fields = result.fields
      autoMapHint.value = result.hint
    }
  } finally {
    autoMapLoading.value = false
  }
}

function addField() {
  draft.value.fields.push({ db_col: '', xml_attr: '' })
}

function removeField(fi) {
  draft.value.fields.splice(fi, 1)
  if (!draft.value.fields.length) {
    draft.value.fields.push({ db_col: '', xml_attr: '' })
  }
}

function close() {
  emit('close')
}

function finish() {
  emit('finish', {
    target_element: draft.value.target_element,
    target_path: draft.value.target_path || '',
    query: draft.value.query,
    fields: draft.value.fields.map((f) => ({ ...f })),
    db_alias: draft.value.db_alias,
    _presetSource: null,
  })
  close()
}
</script>

<style scoped>
.wizard-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: color-mix(in srgb, var(--text) 30%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.wizard-dialog {
  width: min(520px, 100%);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 32px color-mix(in srgb, var(--text) 20%, transparent);
}

.wizard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.wizard-header h3 {
  margin: 0;
  font-size: 15px;
}

.wizard-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}

.wizard-step {
  background: none;
  border: 1px solid transparent;
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-muted);
  padding: 3px 8px;
  cursor: pointer;
}

.wizard-step.active {
  color: var(--accent);
  border-color: var(--accent);
  font-weight: 600;
}

.wizard-step.done {
  color: var(--text);
}

.wizard-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.wizard-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wizard-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.wizard-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
}

.wizard-error {
  font-size: 12px;
  color: var(--danger);
  margin: 0;
}

.wizard-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
}

.review-list {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 6px 12px;
  font-size: 13px;
  margin: 0;
}

.review-list dt {
  color: var(--text-muted);
  font-weight: 500;
}

.review-list dd {
  margin: 0;
}

.review-query {
  font-family: monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
}

.review-fields {
  margin: 0;
  padding-left: 16px;
}

.preview-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

.preview-badge.ok {
  color: var(--success);
  background: color-mix(in srgb, var(--success) 15%, transparent);
}

.preview-badge.warn {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 15%, transparent);
}

.preview-badge.error {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 15%, transparent);
}

.preview-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.preview-table th,
.preview-table td {
  padding: 4px 8px;
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
  margin: 8px 0 0;
  padding-left: 18px;
}

.mapping-warnings {
  font-size: 12px;
  color: var(--warning);
  margin: 4px 0 0;
  padding-left: 18px;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 6px;
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
}

.btn-add-field {
  background: none;
  border: 1px dashed var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 3px 8px;
  align-self: flex-start;
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
}
</style>
