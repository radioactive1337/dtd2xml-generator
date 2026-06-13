<template>
  <div class="tab-pane">
    <div class="field">
      <label>Стратегия заполнения</label>
      <select :value="fillStrategy" @change="$emit('update:fillStrategy', $event.target.value)">
        <option value="faker">Faker (быстро, локально)</option>
        <option value="ai">AI / LLM (контекстная генерация)</option>
        <option value="hybrid_db_faker">Гибрид: БД + Faker</option>
        <option value="hybrid_db_ai">Гибрид: БД + AI</option>
      </select>
    </div>

    <label class="auto-validate-label">
      <input
        type="checkbox"
        :checked="autoValidateAfterFill"
        @change="$emit('update:autoValidateAfterFill', $event.target.checked)"
      />
      Проверять DTD после заполнения
    </label>

    <div v-if="isHybridStrategy" class="db-overrides-panel">
      <div class="overrides-header">
        <div class="overrides-header-top">
          <span class="overrides-title">Подстановка из БД</span>
          <div class="mapping-preset-actions">
            <input
              :value="mappingPresetName"
              placeholder="Имя пресета"
              class="preset-input"
              @input="$emit('update:mappingPresetName', $event.target.value)"
            />
            <button
              class="btn-secondary"
              :disabled="!mappingPresetName"
              @click="$emit('save-mapping-preset')"
            >
              Сохранить
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
                  Нет сохранённых пресетов
                </p>
                <label
                  v-for="p in mappingPresets"
                  :key="p.name"
                  class="preset-dropdown-item"
                >
                  <input
                    type="checkbox"
                    :checked="selectedMappingPresetNames.includes(p.name)"
                    :value="p.name"
                    @change="onPresetCheckboxChange(p.name, $event.target.checked)"
                  />
                  <span class="preset-dropdown-item-label">
                    <span class="preset-dropdown-item-name">{{ p.name }}</span>
                    <span class="preset-meta">
                      {{ formatMappings(p.mapping_count) }}
                    </span>
                  </span>
                  <button
                    class="btn-icon-remove"
                    title="Удалить пресет"
                    @click.prevent="$emit('delete-mapping-preset', p.name)"
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
              title="Убрать пресет"
              @click="$emit('remove-selected-preset', name)"
            >
              ×
            </button>
          </span>
        </div>
        <span class="overrides-hint">Этап 1 — сначала БД, затем Faker/AI для остального</span>
      </div>

      <div v-for="(mapping, mi) in sqlMappings" :key="mi" class="mapping-card">
        <div class="mapping-header">
          <div class="mapping-header-left">
            <span class="mapping-title">Маппинг {{ mi + 1 }}</span>
            <span v-if="mapping._presetSource" class="mapping-preset-badge">{{ mapping._presetSource }}</span>
            <span
              v-if="mappingPreview[mi] && !mappingPreview[mi].loading && mappingPreview[mi].columns?.length"
              class="preview-badge"
              :class="mappingPreview[mi].row === null ? 'warn' : 'ok'"
            >
              {{ mappingPreview[mi].row === null ? '0 строк' : 'OK' }}
            </span>
          </div>
          <div class="mapping-header-right">
            <button class="btn-mapping-edit" @click="$emit('open-mapping-wizard', mi)">Изменить</button>
            <button class="btn-icon-remove" @click="$emit('remove-mapping', mi)" title="Удалить маппинг">×</button>
          </div>
        </div>

        <dl class="mapping-summary">
          <dt>Алиас БД</dt>
          <dd>{{ mapping.db_alias || '—' }}</dd>
          <dt>Целевой элемент</dt>
          <dd>{{ mapping.target_element || '—' }}</dd>
          <dt>Путь к элементу</dt>
          <dd>{{ mapping.target_path || '(все совпадающие теги)' }}</dd>
          <dt>SQL-запрос</dt>
          <dd class="mapping-summary-query">{{ mapping.query || '—' }}</dd>
          <dt>Поля</dt>
          <dd>
            <ul v-if="filledMappingFields(mapping).length" class="mapping-summary-fields">
              <li v-for="f in filledMappingFields(mapping)" :key="f.db_col + f.xml_attr">
                {{ f.db_col }} → {{ f.xml_attr }}
              </li>
            </ul>
            <span v-else>—</span>
          </dd>
        </dl>

        <ul v-if="mappingValidation[mi]?.errors?.length" class="mapping-errors">
          <li v-for="(err, i) in mappingValidation[mi].errors" :key="'e' + i">{{ err }}</li>
        </ul>
        <ul v-if="mappingValidation[mi]?.warnings?.length" class="mapping-warnings">
          <li v-for="(w, i) in mappingValidation[mi].warnings" :key="'w' + i">{{ w }}</li>
        </ul>
      </div>

      <div class="mapping-add-row">
        <button class="btn-add-mapping" @click="$emit('open-mapping-wizard')">+ Добавить маппинг</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { formatMappings } from '../../utils/ruPlural'

const props = defineProps({
  fillStrategy: { type: String, default: 'faker' },
  autoValidateAfterFill: { type: Boolean, default: true },
  isHybridStrategy: { type: Boolean, default: false },
  mappingPresetName: { type: String, default: '' },
  selectedMappingPresetNames: { type: Array, default: () => [] },
  mappingPresets: { type: Array, default: () => [] },
  presetDropdownLabel: { type: String, default: '' },
  sqlMappings: { type: Array, default: () => [] },
  mappingPreview: { type: Object, default: () => ({}) },
  mappingValidation: { type: Array, default: () => [] },
})

const emit = defineEmits([
  'update:fillStrategy',
  'update:autoValidateAfterFill',
  'update:mappingPresetName',
  'update:selectedMappingPresetNames',
  'save-mapping-preset',
  'open-mapping-wizard',
  'remove-mapping',
  'delete-mapping-preset',
  'remove-selected-preset',
])

const presetDropdownOpen = ref(false)
const presetDropdownRef = ref(null)

function filledMappingFields(mapping) {
  return (mapping.fields || []).filter((f) => f.db_col && f.xml_attr)
}

function onPresetCheckboxChange(name, checked) {
  const current = [...(props.selectedMappingPresetNames || [])]
  if (checked && !current.includes(name)) {
    emit('update:selectedMappingPresetNames', [...current, name])
  } else if (!checked) {
    emit('update:selectedMappingPresetNames', current.filter((n) => n !== name))
  }
}

function onPresetDropdownOutsideClick(event) {
  if (!presetDropdownOpen.value || !presetDropdownRef.value) return
  if (!presetDropdownRef.value.contains(event.target)) {
    presetDropdownOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onPresetDropdownOutsideClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onPresetDropdownOutsideClick)
})
</script>

<style scoped>
.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
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

@container (max-width: 520px) {
  .mapping-preset-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .mapping-preset-actions .preset-input,
  .mapping-preset-actions .preset-dropdown-trigger {
    width: 100%;
    min-width: 0;
  }

  .overrides-header-top {
    flex-direction: column;
    align-items: stretch;
  }
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

.btn-mapping-edit {
  background: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
  padding: 2px 8px;
  transition: color 0.15s, border-color 0.15s;
}

.btn-mapping-edit:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.mapping-summary {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 4px 12px;
  font-size: 12px;
  margin: 0;
}

.mapping-summary dt {
  color: var(--text-muted);
  font-weight: 500;
}

.mapping-summary dd {
  margin: 0;
  word-break: break-word;
}

.mapping-summary-query {
  font-family: monospace;
  font-size: 11px;
  white-space: pre-wrap;
}

.mapping-summary-fields {
  margin: 0;
  padding-left: 16px;
}

.mapping-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
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
