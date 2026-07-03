<template>
  <div v-if="open" class="wizard-overlay" @click.self="close">
    <div class="wizard-dialog" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
      <div class="wizard-header">
        <h3 id="wizard-title">{{ isEditMode ? 'Изменить маппинг' : 'Добавить маппинг' }}</h3>
        <button class="btn-icon-remove" title="Закрыть" @click="close">×</button>
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
          <label>Целевой элемент</label>
          <ElementPicker
            v-model="draft.target_element"
            :elements="elements"
            placeholder="Имя элемента (введите или выберите из списка)"
            @update:model-value="onTargetElementChange"
          />
          <p class="wizard-hint">Выберите XML-элемент, атрибуты которого будут заполнены из SQL.</p>
        </div>

        <!-- Step 1: Optional path -->
        <div v-if="step === 1" class="wizard-panel">
          <label>Путь к элементу <span class="label-hint">(необязательно)</span></label>
          <input
            v-model="draft.target_path"
            :list="datalistListFor('wizard-path', 'wizard-paths-list')"
            placeholder="PayDoc.client.contact[0] (необязательно)"
            @input="onPathChange"
            @focus="openDatalist('wizard-path')"
            @blur="scheduleCloseDatalist('wizard-path')"
            @change="onPathDatalistChange"
            @keydown.enter="onDatalistEnter($event, 'wizard-path')"
          />
          <p v-if="!pathOptions.length && draft.target_element && props.xmlText?.trim()" class="wizard-hint wizard-hint-warn">
            В текущем XML нет путей для &lt;{{ draft.target_element }}&gt;.
          </p>
          <p v-else-if="pathOptions.length > 1" class="wizard-hint wizard-hint-warn">
            Без пути будут заполнены все теги &lt;{{ draft.target_element }}&gt; в документе.
            Дубликаты: <code>contact[0]</code>, <code>contact[1]</code>.
          </p>
          <datalist id="wizard-paths-list">
            <option v-for="p in pathOptions" :key="p" :value="p" />
          </datalist>
        </div>

        <!-- Step 2: SQL -->
        <div v-if="step === 2" class="wizard-panel">
          <div class="wizard-row">
            <label>Алиас БД</label>
            <select v-model="draft.db_alias">
              <option value="">Выберите алиас…</option>
              <option v-for="a in dbAliases" :key="a" :value="a">{{ a }}</option>
            </select>
          </div>
          <label>SQL-запрос</label>
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
              {{ preview.loading ? 'Проверка…' : 'Проверить запрос' }}
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
              {{ autoMapLoading ? 'Сопоставление…' : 'Автосопоставление (AI)' }}
            </button>
            <button
              class="btn-secondary"
              :disabled="!preview.columns?.length"
              @click="addAllColumns"
            >
              Добавить все столбцы
            </button>
          </div>
          <p v-if="autoMapHint" class="wizard-hint">{{ autoMapHint }}</p>
          <div v-for="(field, fi) in draft.fields" :key="fi" class="field-row">
            <input
              v-model="field.db_col"
              class="field-input"
              placeholder="Столбец БД"
            />
            <span class="field-arrow">→</span>
            <input
              v-model="field.xml_attr"
              class="field-input"
              :list="'wizard-attrs-list'"
              placeholder="Атрибут XML"
            />
            <button class="btn-icon-remove" title="Удалить" @click="removeField(fi)">×</button>
          </div>
          <datalist id="wizard-attrs-list">
            <option v-for="attr in xmlAttrs" :key="attr" :value="attr" />
          </datalist>
          <button class="btn-add-field" @click="addField">+ Добавить поле</button>
        </div>

        <!-- Step 4: Review -->
        <div v-if="step === 4" class="wizard-panel">
          <dl class="review-list">
            <dt>Элемент</dt>
            <dd>{{ draft.target_element || '—' }}</dd>
            <dt>Путь</dt>
            <dd>{{ draft.target_path || '(все совпадающие теги)' }}</dd>
            <dt>Алиас БД</dt>
            <dd>{{ draft.db_alias || '—' }}</dd>
            <dt>SQL-запрос</dt>
            <dd class="review-query">{{ draft.query || '—' }}</dd>
            <dt>Поля</dt>
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
        <button class="btn-secondary" :disabled="step === 0" @click="step -= 1">Назад</button>
        <button v-if="step < 4" class="btn-primary" :disabled="!canAdvance" @click="step += 1">
          Далее
        </button>
        <button v-else class="btn-primary" :disabled="validation.errors.length" @click="finish">
          {{ isEditMode ? 'Сохранить маппинг' : 'Добавить маппинг' }}
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
  buildFieldsFromSqlColumns,
  mappingsToFields,
  normalizeFieldName,
} from '../utils/mappingUtils'
import { extractXmlElementPaths } from '../utils/xmlPaths'
import {
  datalistListFor,
  openDatalist,
  scheduleCloseDatalist,
  confirmDatalistPick,
  isOptionSelected,
} from '../utils/datalistInput'
import ElementPicker from './ElementPicker.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  initialMapping: { type: Object, default: null },
  schemaId: { type: String, default: '' },
  xmlText: { type: String, default: '' },
  elements: { type: Array, default: () => [] },
  elementAttributes: { type: Object, default: () => ({}) },
  dbAliases: { type: Array, default: () => [] },
  llmAlias: { type: String, default: '' },
  availablePaths: { type: Array, default: () => [] },
})

const isEditMode = computed(() => !!props.initialMapping)

const emit = defineEmits(['close', 'finish'])

const stepLabels = ['Элемент', 'Путь', 'SQL', 'Поля', 'Обзор']
const step = ref(0)

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

const pathOptions = computed(() => {
  const tag = draft.value.target_element?.trim()
  if (!tag) return []

  const text = props.xmlText?.trim()
  if (text) {
    // skipFormat: xmlText comes from liveXmlText which may be mid-edit;
    // xml-formatter cannot recover structurally invalid XML anyway.
    const parsed = extractXmlElementPaths(text, { skipFormat: true })
    if (parsed?.elementPaths?.length) {
      return pathsEndingWithTag(parsed.elementPaths, tag)
    }
  }

  return pathsEndingWithTag(props.availablePaths, tag)
})

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
  if (preview.value.error) return { kind: 'error', text: 'Ошибка' }
  if (!preview.value.columns?.length && !preview.value.error) return null
  if (preview.value.row === null) return { kind: 'warn', text: '0 строк' }
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

function draftFromMapping(mapping) {
  if (!mapping) return createEmptyDraft()
  return {
    target_element: mapping.target_element || '',
    target_path: mapping.target_path || '',
    query: mapping.query || '',
    fields: mapping.fields?.length
      ? mapping.fields.map((f) => ({ db_col: f.db_col || '', xml_attr: f.xml_attr || '' }))
      : [{ db_col: '', xml_attr: '' }],
    db_alias: mapping.db_alias || '',
  }
}

watch(
  () => [props.open, props.initialMapping],
  ([isOpen, initialMapping]) => {
    if (!isOpen) return
    step.value = 0
    draft.value = draftFromMapping(initialMapping)
    preview.value = { loading: false, columns: [], row: undefined, error: '' }
    autoMapHint.value = ''
    if (initialMapping?.db_alias?.trim() && initialMapping?.query?.trim()) {
      testQuery()
    }
  },
)

function onDatalistEnter(event, key) {
  confirmDatalistPick(key)
  event.target.blur()
}

function onTargetElementChange(value) {
  if (draft.value.target_path) {
    const seg = lastPathSegment(draft.value.target_path)
    if (seg !== value) {
      draft.value.target_path = ''
    }
  }
}

function onPathChange() {
  const seg = lastPathSegment(draft.value.target_path)
  if (seg) draft.value.target_element = seg
}

function onPathDatalistChange(event) {
  onPathChange()
  const input = event.target
  if (!input.value || isOptionSelected(input, pathOptions.value)) {
    confirmDatalistPick('wizard-path')
  }
}

function formatPreviewValue(val) {
  if (val === null || val === undefined) return '—'
  return String(val)
}

function autoMapHintForMatcher(matcher) {
  if (matcher === 'llm') {
    return 'Сопоставлено через AI по документации DTD.'
  }
  if (matcher === 'unavailable') {
    return 'LLM не настроен — использовано локальное сопоставление.'
  }
  return 'Использовано локальное сопоставление по именам полей.'
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
      llmAlias: props.llmAlias || undefined,
    })
    return {
      fields: mappingsToFields(mappings),
      hint: autoMapHintForMatcher(matcher),
    }
  } catch (e) {
    return {
      fields: buildFieldMappingsFromColumns(columns, xmlAttrs.value, filled),
      hint: `Ошибка AI-сопоставления (${e.message}) — использовано локальное сопоставление.`,
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
  } catch (e) {
    preview.value = {
      loading: false,
      columns: [],
      row: undefined,
      error: e.message || 'Ошибка запроса',
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

function addAllColumns() {
  const columns = preview.value.columns || []
  if (!columns.length) return
  draft.value.fields = buildFieldsFromSqlColumns(columns, draft.value.fields)
  autoMapHint.value = ''
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

.wizard-hint-warn {
  color: var(--warning);
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
