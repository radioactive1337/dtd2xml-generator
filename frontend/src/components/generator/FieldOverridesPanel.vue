<template>
  <details class="field-overrides" :open="expanded" @toggle="onToggle">
    <summary class="overrides-summary">
      <span>Фиксированные значения полей</span>
      <span v-if="filledCount" class="override-badge">
        {{ overrideBadge }}
      </span>
      <span v-if="filledCount && !applyOnFill" class="override-badge override-badge--off">
        не применяются
      </span>
      <label class="apply-label" @click.stop @mousedown.stop>
        <input
          type="checkbox"
          :checked="applyOnFill"
          @change="$emit('update:applyOnFill', $event.target.checked)"
          @click.stop
          @mousedown.stop
        />
        Применять
      </label>
    </summary>

    <div class="overrides-body" :class="{ 'overrides-body--disabled': !applyOnFill }">
      <p class="overrides-hint">
        Эти значения всегда перезаписывают XML. Снимите «Применять», чтобы не использовать список в этом запуске.
      </p>

      <p v-if="!pathOptions.length && xmlText?.trim()" class="overrides-warn">
        В текущем XML нет путей — сгенерируйте или вставьте XML.
      </p>

      <ul v-if="rows.length" class="override-list">
        <li v-for="(row, index) in rows" :key="index" class="override-row">
          <input
            :value="row.target_path"
            :list="datalistListFor(`fo-path-${index}`, 'field-override-paths')"
            class="path-input"
            placeholder="PayDoc.Body.client[0]"
            @input="$emit('update-row', index, 'target_path', $event.target.value)"
            @focus="openDatalist(`fo-path-${index}`)"
            @blur="scheduleCloseDatalist(`fo-path-${index}`)"
          />
          <input
            :value="row.xml_attr"
            class="attr-input"
            placeholder="inn"
            @input="$emit('update-row', index, 'xml_attr', $event.target.value)"
          />
          <input
            :value="row.value"
            class="value-input"
            placeholder="7707083893"
            @input="$emit('update-row', index, 'value', $event.target.value)"
          />
          <button type="button" class="remove-btn" title="Удалить" @click="$emit('remove-row', index)">
            ×
          </button>
        </li>
      </ul>

      <datalist id="field-override-paths">
        <option v-for="p in pathOptions" :key="p" :value="p" />
      </datalist>

      <button type="button" class="add-btn" @click.stop="onAddRow">+ Добавить поле</button>
    </div>
  </details>
</template>

<script setup>
import { computed, ref } from 'vue'
import { extractXmlElementPaths } from '../../utils/xmlPaths'
import { formatCount } from '../../utils/ruPlural'
import { datalistListFor, openDatalist, scheduleCloseDatalist } from '../../utils/datalistInput'

const props = defineProps({
  rows: { type: Array, required: true },
  xmlText: { type: String, default: '' },
  applyOnFill: { type: Boolean, default: true },
})

const emit = defineEmits(['add-row', 'remove-row', 'update-row', 'update:applyOnFill'])

const expanded = ref(false)

const pathOptions = computed(() => {
  const parsed = extractXmlElementPaths(props.xmlText, { skipFormat: true })
  return parsed?.elementPaths || []
})

const filledCount = computed(
  () => props.rows.filter((r) => r.target_path?.trim() && r.xml_attr?.trim()).length,
)
const overrideBadge = computed(() =>
  formatCount(filledCount.value, 'поле', 'поля', 'полей'),
)

function onToggle(event) {
  expanded.value = event.target.open
}

function onAddRow() {
  expanded.value = true
  emit('add-row')
}
</script>

<style scoped>
.field-overrides {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  background: color-mix(in srgb, var(--border) 15%, transparent);
}

.overrides-summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.overrides-summary::-webkit-details-marker {
  display: none;
}

.override-badge {
  font-size: 10px;
  font-weight: 600;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border-radius: 8px;
  padding: 1px 6px;
}

.override-badge--off {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 14%, transparent);
}

.apply-label {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
}

.apply-label input[type="checkbox"] {
  width: 14px;
  height: 14px;
  min-width: 14px;
  padding: 0;
  margin: 0;
  accent-color: var(--accent);
}

.overrides-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.overrides-body--disabled .override-list,
.overrides-body--disabled .add-btn {
  opacity: 0.45;
  pointer-events: none;
}

.overrides-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
}

.overrides-warn {
  font-size: 11px;
  color: var(--warning);
  margin: 0;
}

.override-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.override-row {
  display: grid;
  grid-template-columns: 1fr 80px 1fr 24px;
  gap: 6px;
  align-items: center;
}

.path-input,
.attr-input,
.value-input {
  min-width: 0;
  font-size: 12px;
  padding: 4px 6px;
}

.remove-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0;
}

.remove-btn:hover {
  color: var(--danger);
}

.add-btn {
  align-self: flex-start;
  background: none;
  border: 1px dashed var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 4px 10px;
}

.add-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}

@container (max-width: 520px) {
  .override-row {
    grid-template-columns: 1fr 1fr;
    grid-template-areas:
      "path path"
      "attr value"
      "remove remove";
  }

  .path-input { grid-area: path; }
  .attr-input { grid-area: attr; }
  .value-input { grid-area: value; }
  .remove-btn { grid-area: remove; justify-self: end; }
}
</style>
