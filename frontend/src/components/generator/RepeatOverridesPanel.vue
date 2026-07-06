<template>
  <details class="repeat-overrides" :open="hasOverrides">
    <summary class="repeat-summary">
      <span>Число повторов (+ / *)</span>
      <span v-if="hasOverrides" class="override-badge">
        {{ overrideBadge }}
      </span>
    </summary>

    <div class="repeat-body">
      <div class="default-row">
        <label class="default-label">По умолчанию</label>
        <input
          :value="repeatCount"
          type="number"
          min="1"
          max="100"
          class="count-input"
          @input="$emit('update:repeatCount', clampCount($event.target.value))"
        />
      </div>

      <p v-if="!repeatablePaths.length" class="repeat-hint">
        Нет элементов с квантификатором + или * в выбранном дереве.
      </p>

      <ul v-else-if="overrideRows.length" class="override-list">
        <li v-for="row in overrideRows" :key="row.path" class="override-row">
          <span class="override-path" :title="row.path">{{ row.label }}</span>
          <input
            :value="row.count"
            type="number"
            min="1"
            max="100"
            class="count-input"
            @input="updateOverride(row.path, clampCount($event.target.value))"
          />
          <button type="button" class="remove-btn" title="Убрать" @click="removeOverride(row.path)">
            ×
          </button>
        </li>
      </ul>

      <div v-if="availablePaths.length" class="add-row">
        <select v-model="selectedPath" class="path-select">
          <option value="">Добавить элемент…</option>
          <option v-for="item in availablePaths" :key="item.path" :value="item.path">
            {{ formatRepeatableLabel(item) }}
          </option>
        </select>
        <button type="button" class="add-btn" :disabled="!selectedPath" @click="addOverride">
          Добавить
        </button>
      </div>
    </div>
  </details>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { formatRepeatableLabel } from '../../utils/repeatablePaths'
import { formatCount } from '../../utils/ruPlural'

const props = defineProps({
  repeatCount: { type: Number, default: 1 },
  repeatOverrides: { type: Object, default: () => ({}) },
  repeatablePaths: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:repeatCount', 'update:repeatOverrides'])

const selectedPath = ref('')

const overrideCount = computed(() => Object.keys(props.repeatOverrides).length)
const hasOverrides = computed(() => overrideCount.value > 0)
const overrideBadge = computed(() =>
  formatCount(overrideCount.value, 'своё', 'своих', 'своих'),
)

const pathByKey = computed(() => {
  const map = new Map()
  for (const item of props.repeatablePaths) {
    map.set(item.path, item)
  }
  return map
})

const overrideRows = computed(() =>
  Object.entries(props.repeatOverrides)
    .map(([path, count]) => {
      const item = pathByKey.value.get(path)
      return {
        path,
        count,
        label: item ? formatRepeatableLabel(item) : path,
      }
    })
    .sort((a, b) => a.path.localeCompare(b.path)),
)

const availablePaths = computed(() =>
  props.repeatablePaths.filter((item) => !(item.path in props.repeatOverrides)),
)

watch(
  () => props.repeatablePaths,
  () => {
    selectedPath.value = ''
    pruneStaleOverrides()
  },
)

function clampCount(raw) {
  const n = Number(raw)
  if (!Number.isFinite(n)) return 1
  return Math.min(100, Math.max(1, Math.round(n)))
}

function pruneStaleOverrides() {
  const valid = new Set(props.repeatablePaths.map((p) => p.path))
  const next = {}
  let changed = false
  for (const [path, count] of Object.entries(props.repeatOverrides)) {
    if (valid.has(path)) {
      next[path] = count
    } else {
      changed = true
    }
  }
  if (changed) emit('update:repeatOverrides', next)
}

function updateOverride(path, count) {
  emit('update:repeatOverrides', { ...props.repeatOverrides, [path]: count })
}

function removeOverride(path) {
  const next = { ...props.repeatOverrides }
  delete next[path]
  emit('update:repeatOverrides', next)
}

function addOverride() {
  if (!selectedPath.value) return
  emit('update:repeatOverrides', {
    ...props.repeatOverrides,
    [selectedPath.value]: props.repeatCount,
  })
  selectedPath.value = ''
}
</script>

<style scoped>
.repeat-overrides {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface-2, var(--bg));
}

.repeat-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
  user-select: none;
  list-style: none;
}

.repeat-summary::-webkit-details-marker {
  display: none;
}

.override-badge {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}

.repeat-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 10px 10px;
  border-top: 1px solid var(--border);
}

.default-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
}

.default-label {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.count-input {
  width: 72px;
}

.repeat-hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
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
  display: flex;
  align-items: center;
  gap: 6px;
}

.override-path {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-btn {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}

.remove-btn:hover {
  color: var(--danger);
}

.add-row {
  display: flex;
  gap: 6px;
}

.path-select {
  flex: 1;
  min-width: 0;
  font-size: 12px;
}

.add-btn {
  flex-shrink: 0;
  font-size: 12px;
  white-space: nowrap;
}

.add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
