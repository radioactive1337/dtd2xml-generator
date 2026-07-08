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

    <div class="library-search-row">
      <div class="library-search-wrap">
        <span class="library-search-icon">⌕</span>
        <input
          v-model="searchQuery"
          type="search"
          class="library-search-input"
          :placeholder="activeScope === 'shared' ? 'Поиск по категориям и документам…' : 'Поиск по названию, описанию…'"
          autocomplete="off"
          @keydown.escape="searchQuery = ''"
        />
        <button
          v-if="searchQuery"
          type="button"
          class="library-search-clear"
          aria-label="Очистить поиск"
          @click="searchQuery = ''"
        >×</button>
      </div>
      <span v-if="searchQuery && activeScope === 'shared'" class="library-search-count">
        {{ searchMatchCount }}
      </span>
      <span v-if="searchQuery && activeScope === 'personal'" class="library-search-count">
        {{ filteredPersonalDocuments.length }}
      </span>
    </div>

    <p v-if="libraryError" class="library-error" role="alert">{{ libraryError }}</p>

    <div v-if="activeScope === 'shared'" class="library-pane">
      <div v-if="syncStatus?.enabled" class="shared-toolbar">
        <button
          type="button"
          class="btn-secondary btn-sm"
          :disabled="syncing || !canSyncFromGit"
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

      <div
        v-if="syncStatus?.enabled && syncStatus?.git_auth_required && !syncStatus?.git_configured"
        class="library-hint"
      >
        Для доступа к приватному репозиторию укажите Git-токен в
        <router-link to="/settings">Настройках</router-link>.
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

      <ul v-if="searchFilteredCategories.length" class="category-list">
        <li v-for="cat in searchFilteredCategories" :key="cat.name" class="category-item">
          <button
            type="button"
            class="category-toggle"
            :aria-expanded="isCategoryExpanded(cat.name)"
            @click="toggleCategory(cat.name)"
          >
            <span class="category-chevron" :class="{ 'category-chevron--open': isCategoryExpanded(cat.name) }">▶</span>
            <span class="category-name" v-html="highlightMatch(cat.name, searchQuery)" />
            <span v-if="cat.root_element" class="category-root">{{ cat.root_element }}</span>
            <span class="category-count">({{ cat.document_count }})</span>
          </button>
          <ul v-if="isCategoryExpanded(cat.name)" class="doc-list">
            <template v-if="isCategoryLoading(cat.name)">
              <li class="doc-loading">Загрузка…</li>
            </template>
            <template v-else>
              <li
                v-for="doc in getVisibleDocs(cat.name)"
                :key="doc.doc_id"
                class="doc-item"
              >
                <span class="doc-title" v-html="highlightMatch(doc.title, searchQuery)" />
                <button
                  type="button"
                  class="btn-secondary btn-sm"
                  @click="$emit('open-shared', cat.name, doc.doc_id)"
                >
                  Открыть
                </button>
              </li>
              <li
                v-if="categoryDocuments[cat.name] !== undefined && getVisibleDocs(cat.name).length === 0"
                class="doc-loading"
              >
                {{ searchQuery ? 'Документов с таким названием нет' : 'Нет документов' }}
              </li>
            </template>
          </ul>
        </li>
      </ul>
      <p v-else-if="searchQuery && !searchFilteredCategories.length" class="library-hint">
        По запросу «{{ searchQuery }}» ничего не найдено.
      </p>
    </div>

    <div v-else class="library-pane">
      <ul v-if="filteredPersonalDocuments.length" class="doc-list doc-list--flat">
        <li v-for="doc in filteredPersonalDocuments" :key="doc.name" class="doc-item">
          <div class="doc-info">
            <span class="doc-title" v-html="highlightMatch(doc.name, searchQuery)" />
            <span
              v-if="currentSchemaId && doc.schema_id && doc.schema_id !== currentSchemaId"
              class="doc-schema-hint"
            >
              другая схема DTD
            </span>
            <span v-if="doc.shared_by_name" class="doc-shared-badge">от {{ doc.shared_by_name }}</span>
            <span
              v-if="doc.description"
              class="doc-desc"
              v-html="highlightMatch(doc.description, searchQuery)"
            />
          </div>
          <div class="doc-actions">
            <button
              type="button"
              class="btn-secondary btn-sm"
              title="Поделиться"
              @click="$emit('share-personal', doc.name)"
            >
              Поделиться
            </button>
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
      <p v-else-if="!loading && !searchQuery" class="library-hint">Нет сохранённых документов.</p>
      <p v-else-if="!loading && searchQuery" class="library-hint">
        По запросу «{{ searchQuery }}» ничего не найдено.
      </p>
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
  'share-personal',
  'delete-personal',
])

const canSyncFromGit = computed(() => {
  const status = props.syncStatus
  if (!status?.enabled) return false
  if (status.git_auth_required && !status.git_configured) return false
  return true
})

const expandedCategory = ref(null)
const categoryRootFilter = ref('')
const searchQuery = ref('')

// Reset search when switching scopes
watch(() => props.activeScope, () => { searchQuery.value = '' })

// ── Root-element picker ──────────────────────────────────────────────────────

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

// ── Text search helpers ──────────────────────────────────────────────────────

function normalizeSearch(s) {
  return (s || '').toLowerCase().trim()
}

function textContains(text, query) {
  if (!query) return true
  return normalizeSearch(text).includes(normalizeSearch(query))
}

function highlightMatch(text, query) {
  if (!query || !text) return escapeHtml(text || '')
  const escaped = escapeHtml(text)
  const escapedQuery = escapeHtml(query.trim())
  if (!escapedQuery) return escaped
  const regex = new RegExp(`(${escapedQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
  return escaped.replace(regex, '<mark class="search-highlight">$1</mark>')
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// ── Shared search ────────────────────────────────────────────────────────────

// Track categories where expand-category was emitted but docs haven't arrived yet.
// Using a plain reactive object so Vue tracks property add/delete.
const pendingLoadCategories = ref({})

function requestCategoryLoad(name) {
  if (
    !props.categoryDocuments[name] &&
    props.loadingCategory !== name &&
    !pendingLoadCategories.value[name]
  ) {
    pendingLoadCategories.value[name] = true
    emit('expand-category', name)
  }
}

// When docs arrive for a pending category, clear its pending flag.
watch(
  () => props.categoryDocuments,
  (docs) => {
    for (const name of Object.keys(pendingLoadCategories.value)) {
      if (docs[name] !== undefined) {
        delete pendingLoadCategories.value[name]
      }
    }
  },
  { deep: false },
)

// Categories that match the root-element filter AND the text search query.
// Categories with no loaded docs but matching name/root_element are always included —
// they'll show a loading indicator while their docs are fetched.
const searchFilteredCategories = computed(() => {
  const rootFiltered = filteredCategories.value
  const q = normalizeSearch(searchQuery.value)
  if (!q) return rootFiltered

  return rootFiltered.filter((cat) => {
    if (textContains(cat.name, q)) return true
    if (textContains(cat.root_element, q)) return true
    // Check already-loaded docs for title match
    const docs = props.categoryDocuments[cat.name]
    if (docs) return docs.some((d) => textContains(d.title, q))
    // Category docs not yet loaded — exclude from results by title,
    // but keep if name/root_element already matched above.
    return false
  })
})

// Trigger lazy loading for all visible categories whenever search query changes.
watch(searchQuery, (q) => {
  if (!q) {
    pendingLoadCategories.value = {}
    return
  }
  for (const cat of searchFilteredCategories.value) {
    requestCategoryLoad(cat.name)
  }
})

// Also trigger when filtered set changes (e.g. root-element filter applied alongside text search).
watch(searchFilteredCategories, (cats) => {
  if (!searchQuery.value) return
  for (const cat of cats) {
    requestCategoryLoad(cat.name)
  }
})

// A category is "expanded" when:
//   - manually toggled, OR
//   - search is active and docs are loaded / loading / pending
function isCategoryExpanded(name) {
  if (searchQuery.value) {
    return (
      props.categoryDocuments[name] !== undefined ||
      props.loadingCategory === name ||
      !!pendingLoadCategories.value[name]
    )
  }
  return expandedCategory.value === name
}

// True while we're waiting for this category's docs during a search.
function isCategoryLoading(name) {
  return (
    props.loadingCategory === name ||
    (!!searchQuery.value && !!pendingLoadCategories.value[name] && props.categoryDocuments[name] === undefined)
  )
}

function categoryMatchesSearchDirectly(cat, q) {
  return textContains(cat.name, q) || textContains(cat.root_element, q)
}

function getVisibleDocs(catName) {
  const docs = props.categoryDocuments[catName] || []
  const q = normalizeSearch(searchQuery.value)
  if (!q) return docs
  // If the category itself matched (by name or root_element) — show all its docs.
  const cat = props.sharedCategories.find((c) => c.name === catName)
  if (cat && categoryMatchesSearchDirectly(cat, q)) return docs
  // Category matched only because some doc titles match — filter to those docs.
  return docs.filter((d) => textContains(d.title, q))
}

const searchMatchCount = computed(() => {
  let n = 0
  for (const cat of searchFilteredCategories.value) {
    const docs = props.categoryDocuments[cat.name]
    if (docs) n += getVisibleDocs(cat.name).length
    else n += cat.document_count
  }
  return n
})

// ── Personal search ──────────────────────────────────────────────────────────

const filteredPersonalDocuments = computed(() => {
  const q = normalizeSearch(searchQuery.value)
  if (!q) return props.personalDocuments
  return props.personalDocuments.filter(
    (doc) =>
      textContains(doc.name, q) ||
      textContains(doc.description, q) ||
      textContains(doc.shared_by_name, q),
  )
})

// ── Watchers ─────────────────────────────────────────────────────────────────

watch(
  () => props.rootElement,
  (val) => {
    if (val && !categoryRootFilter.value) {
      categoryRootFilter.value = val
    }
  },
  { immediate: true },
)

// ── Handlers ─────────────────────────────────────────────────────────────────

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
  if (expandedCategory.value === name && !searchQuery.value) {
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

.doc-shared-badge {
  font-size: 10px;
  color: var(--accent);
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

.btn-sm {
  padding: 4px 8px;
  font-size: 11px;
}

.btn-icon {
  min-width: 24px;
  padding: 4px 6px;
  line-height: 1;
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

/* ── Search ─────────────────────────────────────────────────────────────── */

.library-search-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.library-search-wrap {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
}

.library-search-icon {
  position: absolute;
  left: 7px;
  font-size: 14px;
  color: var(--text-muted);
  pointer-events: none;
  line-height: 1;
  top: 50%;
  transform: translateY(-50%);
}

.library-search-input {
  width: 100%;
  padding: 5px 28px 5px 24px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface, #1e1e1e);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.library-search-input:focus {
  border-color: color-mix(in srgb, var(--accent) 60%, var(--border));
}

.library-search-input::-webkit-search-cancel-button {
  display: none;
}

.library-search-clear {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 4px;
}

.library-search-clear:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--border) 40%, transparent);
}

.library-search-count {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

:deep(.search-highlight) {
  background: color-mix(in srgb, var(--accent, #4a9eff) 30%, transparent);
  color: var(--text);
  border-radius: 2px;
  padding: 0 1px;
  font-style: normal;
}
</style>
