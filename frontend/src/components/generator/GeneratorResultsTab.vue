<template>
  <div class="tab-pane">
    <div v-if="status" class="results-status" :class="`results-status--${status}`" role="status">
      <span class="results-status-dot" aria-hidden="true" />
      <span>{{ statusMessage }}</span>
    </div>

    <ul v-if="validationResult?.valid === false && validationResult?.errors?.length" class="validation-errors">
      <li v-for="(err, i) in validationResult.errors" :key="i">
        <button
          v-if="err.line"
          type="button"
          class="validation-error-link"
          @click="$emit('go-to-error', err)"
        >
          Строка {{ err.line }}, столбец {{ err.column }}: {{ err.message }}
        </button>
        <span v-else>{{ err.message }}</span>
      </li>
    </ul>

    <p v-if="buildInfo" class="build-info">
      {{ nodesLabel }}
    </p>

    <template v-if="buildInfo?.warnings?.length">
      <p class="build-warnings-heading">
        {{ warningsHeading }}
      </p>
      <ul class="build-warnings">
        <li v-for="(warning, i) in buildInfo.warnings" :key="i">{{ warning }}</li>
      </ul>
    </template>

    <p v-if="xmlSyncHint && status !== 'error'" class="error-msg">{{ xmlSyncHint }}</p>

    <section v-if="history.length" class="history-section">
      <div class="history-header">
        <h3 class="history-title">История генераций</h3>
        <button type="button" class="btn-link" @click="$emit('clear-history')">
          Очистить
        </button>
      </div>
      <ul class="history-list">
        <li v-for="entry in history" :key="entry.id" class="history-item">
          <div class="history-item-main">
            <span class="history-type" :class="`history-type--${entry.type}`">
              {{ typeLabel(entry.type) }}
            </span>
            <span class="history-meta">
              <span class="history-time">{{ formatTimestamp(entry.timestamp) }}</span>
              <span v-if="entry.root_element" class="history-root">{{ entry.root_element }}</span>
              <span v-if="entry.node_count != null" class="history-nodes">
                {{ formatNodes(entry.node_count) }}
              </span>
            </span>
          </div>
          <div class="history-actions">
            <button type="button" class="btn-secondary btn-sm" @click="$emit('restore', entry)">
              Восстановить
            </button>
            <button
              type="button"
              class="btn-secondary btn-sm btn-icon"
              title="Удалить"
              aria-label="Удалить из истории"
              @click="$emit('remove', entry.id)"
            >
              ×
            </button>
          </div>
        </li>
      </ul>
      <p class="history-hint">Сохраняются последние {{ maxEntries }} результатов в браузере.</p>
    </section>

    <XmlLibraryPanel
      :active-scope="libraryActiveScope"
      :shared-categories="sharedCategories"
      :personal-documents="personalDocuments"
      :sync-status="syncStatus"
      :syncing="librarySyncing"
      :loading="libraryLoading"
      :library-error="libraryError"
      :can-save="canSaveLibraryDocument"
      :category-documents="categoryDocuments"
      :loading-category="loadingCategory"
      @update:active-scope="$emit('update:library-active-scope', $event)"
      @sync="$emit('library-sync')"
      @expand-category="(cat) => $emit('library-expand-category', cat)"
      @open-shared="(cat, id) => $emit('library-open-shared', cat, id)"
      @open-personal="(name) => $emit('library-open-personal', name)"
      @delete-personal="(name) => $emit('library-delete-personal', name)"
      @save="(payload) => $emit('library-save', payload)"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import XmlLibraryPanel from './XmlLibraryPanel.vue'
import { formatErrors, formatNodes, formatWarnings } from '../../utils/ruPlural'

const props = defineProps({
  validationResult: { type: Object, default: null },
  buildInfo: { type: Object, default: null },
  xmlSyncHint: { type: String, default: '' },
  history: { type: Array, default: () => [] },
  maxEntries: { type: Number, default: 20 },
  libraryActiveScope: { type: String, default: 'shared' },
  sharedCategories: { type: Array, default: () => [] },
  personalDocuments: { type: Array, default: () => [] },
  syncStatus: { type: Object, default: null },
  librarySyncing: { type: Boolean, default: false },
  libraryLoading: { type: Boolean, default: false },
  libraryError: { type: String, default: '' },
  canSaveLibraryDocument: { type: Boolean, default: false },
  categoryDocuments: { type: Object, default: () => ({}) },
  loadingCategory: { type: String, default: null },
})

defineEmits([
  'go-to-error',
  'restore',
  'remove',
  'clear-history',
  'update:library-active-scope',
  'library-sync',
  'library-expand-category',
  'library-open-shared',
  'library-open-personal',
  'library-delete-personal',
  'library-save',
])

const TYPE_LABELS = {
  generate: 'Генерация',
  fill: 'Заполнение',
}

function typeLabel(type) {
  return TYPE_LABELS[type] || type
}

function formatTimestamp(ts) {
  return new Date(ts).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const status = computed(() => {
  if (props.validationResult?.valid === false && props.validationResult?.errors?.length) return 'error'
  if (props.validationResult?.valid === true) return 'ok'
  if (props.xmlSyncHint) return 'error'
  if (props.buildInfo?.warnings?.length) return 'warn'
  if (props.buildInfo && !props.buildInfo.warnings?.length) return 'ok'
  return null
})

const nodesLabel = computed(() => {
  if (!props.buildInfo) return ''
  return formatNodes(props.buildInfo.node_count)
})

const warningsHeading = computed(() => {
  const count = props.buildInfo?.warnings?.length ?? 0
  return `${formatWarnings(count)}:`
})

const statusMessage = computed(() => {
  if (status.value === 'error') {
    if (props.validationResult?.valid === false && props.validationResult?.errors?.length) {
      const count = props.validationResult.errors.length
      return `Проверка не пройдена — ${formatErrors(count)}`
    }
    return props.xmlSyncHint
  }
  if (status.value === 'warn') {
    const count = props.buildInfo.warnings.length
    if (count === 1) return 'Сборка завершена с 1 предупреждением'
    return `Сборка завершена с ${count} предупреждениями`
  }
  if (props.validationResult?.valid === true) {
    return 'XML соответствует DTD'
  }
  if (props.buildInfo) {
    return `Сгенерировано — ${formatNodes(props.buildInfo.node_count)}, без предупреждений`
  }
  return ''
})
</script>

<style scoped>
.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.results-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid transparent;
}

.results-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.results-status--ok {
  color: var(--success);
  background: color-mix(in srgb, var(--success) 10%, transparent);
  border-color: color-mix(in srgb, var(--success) 35%, var(--border));
}

.results-status--ok .results-status-dot {
  background: var(--success);
}

.results-status--warn {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 10%, transparent);
  border-color: color-mix(in srgb, var(--warning) 35%, var(--border));
}

.results-status--warn .results-status-dot {
  background: var(--warning);
}

.results-status--error {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border-color: color-mix(in srgb, var(--danger) 35%, var(--border));
}

.results-status--error .results-status-dot {
  background: var(--danger);
}

.build-info {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
}

.build-warnings-heading {
  font-size: 12px;
  color: var(--warning);
  margin: 0;
}

.build-warnings {
  font-size: 12px;
  color: var(--warning);
  margin: 0;
  padding-left: 18px;
}

.build-warnings li {
  margin-bottom: 4px;
}

.validation-errors {
  font-size: 12px;
  color: var(--danger);
  margin: 0;
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

.error-msg {
  font-size: 12px;
  color: var(--danger);
  margin: 0;
}

.history-section {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.history-title {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.btn-link {
  padding: 0;
  border: none;
  background: none;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.btn-link:hover {
  color: var(--text);
}

.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--surface) 50%, transparent);
}

.history-item-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.history-type {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.history-type--generate {
  color: var(--accent);
}

.history-type--fill {
  color: var(--success);
}

.history-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.history-root {
  font-family: var(--font-mono, monospace);
}

.history-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 11px;
}

.btn-icon {
  min-width: 24px;
  padding: 4px 6px;
  line-height: 1;
}

.history-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-muted);
}
</style>
