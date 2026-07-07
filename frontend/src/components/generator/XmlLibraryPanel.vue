<template>
  <section class="library-section">
    <div class="library-header">
      <div class="library-tabs" role="tablist">
        <button
          type="button"
          class="library-tab"
          :class="{ 'library-tab--active': activeScope === 'shared' }"
          role="tab"
          :aria-selected="activeScope === 'shared'"
          @click="setScope('shared')"
        >
          Эталоны
        </button>
        <button
          type="button"
          class="library-tab"
          :class="{ 'library-tab--active': activeScope === 'personal' }"
          role="tab"
          :aria-selected="activeScope === 'personal'"
          @click="setScope('personal')"
        >
          Мои документы
        </button>
      </div>
    </div>

    <p v-if="libraryError" class="library-error" role="alert">{{ libraryError }}</p>

    <div v-if="activeScope === 'shared'" class="library-pane">
      <div v-if="syncStatus?.enabled" class="shared-toolbar">
        <button
          type="button"
          class="btn-secondary btn-sm"
          :disabled="syncing"
          @click="onSync"
        >
          {{ syncing ? 'Обновление…' : 'Обновить из Git' }}
        </button>
        <span v-if="syncStatus?.last_sync" class="sync-meta">
          {{ formatSyncTime(syncStatus.last_sync) }}
          <span v-if="syncStatus.commit_sha" class="sync-sha">{{ syncStatus.commit_sha }}</span>
        </span>
      </div>
      <p v-else class="library-hint">Эталонная библиотека не настроена на сервере.</p>

      <div v-if="syncStatus?.enabled && !syncStatus?.configured" class="library-hint">
        Каталог эталонов пуст. Нажмите «Обновить из Git» для первой загрузки.
      </div>

      <div v-if="syncStatus?.enabled" class="field category-search-field">
        <label>Корневой элемент</label>
        <ElementPicker
          v-model="categoryRootFilter"
          :elements="pickerElements"
          :element-docs="elementDocs"
          :show-selected-doc="false"
          placeholder="Имя элемента (введите или выберите из списка)"
          @confirm="onCategoryRootConfirm"
        />
        <p v-if="categoryRootFilter && !filteredCategories.length" class="library-hint">
          Нет папок для выбранного корневого элемента.
        </p>
      </div>

      <ul v-if="filteredCategories.length" class="category-list">
        <li v-for="cat in filteredCategories" :key="cat.name" class="category-item">
          <button
            type="button"
            class="category-toggle"
            :aria-expanded="expandedCategory === cat.name"
            @click="toggleCategory(cat.name)"
          >
            <span class="category-chevron" :class="{ 'category-chevron--open': expandedCategory === cat.name }">▶</span>
            <span class="category-name">{{ cat.name }}</span>
            <span v-if="cat.root_element" class="category-root">{{ cat.root_element }}</span>
            <span class="category-count">({{ cat.document_count }})</span>
          </button>
          <ul v-if="expandedCategory === cat.name" class="doc-list">
            <li v-for="doc in categoryDocuments[cat.name] || []" :key="doc.doc_id" class="doc-item">
              <span class="doc-title">{{ doc.title }}</span>
              <button
                type="button"
                class="btn-secondary btn-sm"
                @click="$emit('open-shared', cat.name, doc.doc_id)"
              >
                Открыть
              </button>
            </li>
            <li v-if="loadingCategory === cat.name" class="doc-loading">Загрузка…</li>
          </ul>
        </li>
      </ul>
    </div>

    <div v-else class="library-pane">
      <button
        type="button"
        class="btn-secondary btn-sm save-btn"
        :disabled="!canSave"
        @click="onSaveClick"
      >
        Сохранить текущий XML
      </button>

      <ul v-if="personalDocuments.length" class="doc-list doc-list--flat">
        <li v-for="doc in personalDocuments" :key="doc.name" class="doc-item">
          <div class="doc-info">
            <span class="doc-title">{{ doc.name }}</span>
            <span
              v-if="currentSchemaId && doc.schema_id && doc.schema_id !== currentSchemaId"
              class="doc-schema-hint"
            >
              другая схема DTD
            </span>
            <span v-if="doc.description" class="doc-desc">{{ doc.description }}</span>
          </div>
          <div class="doc-actions">
            <button
              type="button"
              class="btn-secondary btn-sm"
              @click="$emit('open-personal', doc.name)"
            >
              Открыть
            </button>
            <button
              type="button"
              class="btn-secondary btn-sm btn-icon"
              title="Удалить"
              aria-label="Удалить документ"
              @click="$emit('delete-personal', doc.name)"
            >
              ×
            </button>
          </div>
        </li>
      </ul>
      <p v-else-if="!loading" class="library-hint">Нет сохранённых документов.</p>
    </div>

    <div v-if="showSaveDialog" class="save-dialog-backdrop" @click.self="closeSaveDialog">
      <form class="save-dialog" @submit.prevent="submitSave">
        <h4 class="save-dialog-title">Сохранить XML</h4>
        <label class="save-label">
          Имя
          <input v-model="saveName" type="text" class="save-input" required autofocus />
        </label>
        <label class="save-label">
          Описание (необязательно)
          <input v-model="saveDescription" type="text" class="save-input" />
        </label>
        <div class="save-dialog-actions">
          <button type="button" class="btn-secondary btn-sm" @click="closeSaveDialog">Отмена</button>
          <button type="submit" class="btn-primary btn-sm" :disabled="!saveName.trim()">Сохранить</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import ElementPicker from '../ElementPicker.vue'
import {
  normalizeElementSearchKey,
  resolveElementName,
} from '../../utils/elementFilter'

const props = defineProps({
  activeScope: { type: String, default: 'shared' },
  sharedCategories: { type: Array, default: () => [] },
  personalDocuments: { type: Array, default: () => [] },
  syncStatus: { type: Object, default: null },
  syncing: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  libraryError: { type: String, default: '' },
  canSave: { type: Boolean, default: false },
  categoryDocuments: { type: Object, default: () => ({}) },
  loadingCategory: { type: String, default: null },
  elements: { type: Array, default: () => [] },
  elementDocs: { type: Object, default: () => ({}) },
  rootElement: { type: String, default: '' },
  currentSchemaId: { type: String, default: '' },
})

const emit = defineEmits([
  'update:activeScope',
  'sync',
  'expand-category',
  'open-shared',
  'open-personal',
  'delete-personal',
  'save',
])

const expandedCategory = ref(null)
const categoryRootFilter = ref('')

const showSaveDialog = ref(false)
const saveName = ref('')
const saveDescription = ref('')

const pickerElements = computed(() => {
  const fromSchema = props.elements || []
  const fromCategories = (props.sharedCategories || [])
    .map((cat) => cat.root_element)
    .filter(Boolean)
  return [...new Set([...fromSchema, ...fromCategories])].sort()
})

function categoryMatchesRoot(cat, query) {
  const trimmed = (query || '').trim()
  if (!trimmed) return true
  const resolved = resolveElementName(trimmed, pickerElements.value)
  const key = normalizeElementSearchKey(resolved || trimmed)
  const roots = [
    normalizeElementSearchKey(cat.root_element || ''),
    normalizeElementSearchKey(cat.name || ''),
  ].filter(Boolean)
  return roots.some((rootKey) => rootKey === key || rootKey.includes(key) || key.includes(rootKey))
}

const filteredCategories = computed(() => {
  if (!categoryRootFilter.value.trim()) return props.sharedCategories
  return props.sharedCategories.filter((cat) => categoryMatchesRoot(cat, categoryRootFilter.value))
})

watch(
  () => props.rootElement,
  (val) => {
    if (val && !categoryRootFilter.value) {
      categoryRootFilter.value = val
    }
  },
  { immediate: true },
)

function onCategoryRootConfirm(name) {
  categoryRootFilter.value = name
  const first = filteredCategories.value[0]
  if (first) {
    expandedCategory.value = first.name
    if (!props.categoryDocuments[first.name]) {
      emit('expand-category', first.name)
    }
  }
}

function setScope(scope) {
  emit('update:activeScope', scope)
}

function formatSyncTime(iso) {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function toggleCategory(name) {
  if (expandedCategory.value === name) {
    expandedCategory.value = null
    return
  }
  expandedCategory.value = name
  if (!props.categoryDocuments[name]) {
    emit('expand-category', name)
  }
}

function onSync() {
  emit('sync')
}

function onSaveClick() {
  saveName.value = ''
  saveDescription.value = ''
  showSaveDialog.value = true
}

function closeSaveDialog() {
  showSaveDialog.value = false
}

function submitSave() {
  const name = saveName.value.trim()
  if (!name) return
  emit('save', { name, description: saveDescription.value.trim() })
  closeSaveDialog()
}
</script>

<style scoped>
.library-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.library-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.library-tabs {
  display: flex;
  gap: 4px;
}

.library-tab {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  font-size: 11px;
  cursor: pointer;
  color: var(--text-muted);
}

.library-tab--active {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
  color: var(--text);
}

.library-pane {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.shared-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sync-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.sync-sha {
  font-family: var(--font-mono, monospace);
  margin-left: 4px;
}

.library-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
}

.library-error {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--danger);
}

.category-list,
.doc-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.category-item {
  margin-bottom: 4px;
}

.category-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--surface) 50%, transparent);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
}

.category-chevron {
  font-size: 9px;
  transition: transform 0.15s;
  color: var(--text-muted);
}

.category-chevron--open {
  transform: rotate(90deg);
}

.category-name {
  font-family: var(--font-mono, monospace);
  font-weight: 500;
}

.category-root {
  font-size: 11px;
  color: var(--accent);
  font-family: var(--font-mono, monospace);
}

.category-count {
  color: var(--text-muted);
  font-size: 11px;
}

.doc-list {
  margin: 4px 0 0 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.doc-list--flat {
  margin-left: 0;
}

.doc-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--surface) 50%, transparent);
}

.doc-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.doc-title {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-desc {
  font-size: 10px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-schema-hint {
  font-size: 10px;
  color: var(--warning, #b8860b);
}

.doc-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.doc-loading {
  font-size: 11px;
  color: var(--text-muted);
  padding: 4px 8px;
}

.save-btn {
  align-self: flex-start;
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

.save-dialog-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--bg, #000) 40%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.save-dialog {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  width: min(360px, 90vw);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.save-dialog-title {
  margin: 0;
  font-size: 14px;
}

.save-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.save-input {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
}

.save-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

.category-search-field label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--text-muted);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
