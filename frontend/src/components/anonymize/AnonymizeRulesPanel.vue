<template>
  <div class="rules">
    <p class="hint">
      Правила определяют, какие поля считать ПДн. Общие правила команды лежат в
      <code>config/anonymize_rules.json</code> (только чтение), ваши личные дополняют и переопределяют их.
      Правила растут по мере работы — через «Запомнить как правило» на вкладке «Проверка».
    </p>

    <div class="toolbar">
      <input v-model="r.query" type="search" placeholder="Поиск по элементу, атрибуту, категории…" />
      <select v-model="r.layerFilter" aria-label="Слой правил">
        <option value="all">Все</option>
        <option value="user">Мои</option>
        <option value="global">Общие</option>
      </select>
      <select v-model="r.sourceFilter" aria-label="Источник правила">
        <option value="">Любой источник</option>
        <option value="manual">Вручную</option>
        <option value="heuristic">Эвристика</option>
        <option value="llm_suggested">ИИ</option>
        <option value="builtin">Встроенные</option>
        <option value="import">Импорт</option>
      </select>
    </div>

    <div class="toolbar actions">
      <input ref="fileInput" type="file" accept=".json,application/json" class="hidden-input" @change="onImport" />
      <button type="button" class="btn-secondary btn-sm" @click="fileInput?.click()">Импорт JSON</button>
      <button type="button" class="btn-secondary btn-sm" :disabled="!r.userRules.length" @click="r.exportJson('user')">
        Экспорт моих
      </button>
      <button type="button" class="btn-secondary btn-sm" @click="r.exportJson('all')">Экспорт всех</button>
      <button
        type="button"
        class="btn-secondary btn-sm btn-danger-tint"
        :disabled="!r.userRules.length"
        @click="confirmClear"
      >
        Удалить мои
      </button>
    </div>
    <label class="check">
      <input v-model="replaceOnImport" type="checkbox" />
      <span>При импорте заменить мои правила (иначе — объединить)</span>
    </label>
    <p v-if="r.message" class="hint ok-text">{{ r.message }}</p>
    <p v-if="r.error" class="error-msg">{{ r.error }}</p>

    <p v-if="r.loading" class="hint">Загрузка…</p>
    <p v-else-if="!r.visibleRules.length" class="hint">Правил не найдено.</p>
    <ul v-else class="list">
      <li v-for="rule in r.visibleRules" :key="`${rule.layer}-${rule.id}`" class="rule">
        <div class="rule-main">
          <code class="rule-scope" :title="ruleSummary(rule)">{{ ruleSummary(rule) }}</code>
          <span class="action" :class="rule.action">
            {{ rule.action === 'replace' ? `→ ${categoryLabel(rule.category)}` : 'оставить' }}
          </span>
        </div>
        <div class="rule-meta">
          <span class="tag" :class="rule.layer">{{ rule.layer === 'global' ? 'общее' : 'моё' }}</span>
          <span class="tag">{{ sourceLabel(rule.source) }}</span>
          <span v-if="rule.created_by" class="hint">{{ rule.created_by }}</span>
          <span v-if="rule.note" class="hint" :title="rule.note">{{ rule.note }}</span>
          <button v-if="rule.layer === 'user'" type="button" class="link" @click="r.remove(rule.id)">Удалить</button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ruleSummary } from '../../utils/anonymize'

const props = defineProps({ ctx: { type: Object, required: true } })

const r = computed(() => props.ctx.rules)
const fileInput = ref(null)
const replaceOnImport = ref(false)

const categoryById = computed(() => new Map(props.ctx.categories.map((c) => [c.id, c.label])))

const SOURCES = {
  manual: 'вручную',
  heuristic: 'эвристика',
  llm_suggested: 'ИИ',
  builtin: 'встроено',
  import: 'импорт',
}

function sourceLabel(source) {
  return SOURCES[source] || source || '—'
}

function categoryLabel(id) {
  return categoryById.value.get(id) || id || '—'
}

async function onImport(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) await r.value.importFile(file, replaceOnImport.value ? 'replace' : 'merge')
}

function confirmClear() {
  if (window.confirm('Удалить все ваши личные правила анонимизации? Общие правила не затрагиваются.')) {
    r.value.clearUser()
  }
}
</script>

<style scoped>
.rules {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted);
}

.ok-text {
  color: var(--success);
}

.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar input[type='search'] {
  flex: 1;
  min-width: 160px;
  padding: 6px 10px;
  font-size: 13px;
}

.toolbar select {
  width: auto;
  padding: 6px 10px;
  font-size: 13px;
}

.hidden-input {
  display: none;
}

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}

.btn-danger-tint {
  color: var(--danger);
}

.check {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12px;
  color: var(--text);
}

.check input {
  width: 14px;
  min-width: 14px;
  height: 14px;
  margin: 0;
  padding: 0;
  accent-color: var(--accent);
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rule {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rule-main,
.rule-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rule-scope {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.action {
  font-size: 12px;
  font-weight: 500;
}

.action.replace {
  color: var(--accent);
}

.action.keep {
  color: var(--text-muted);
}

.tag {
  padding: 1px 7px;
  font-size: 11px;
  border-radius: 10px;
  background: var(--border);
  color: var(--text-muted);
}

.tag.user {
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
}

.link {
  margin-left: auto;
  padding: 0;
  background: none;
  border: none;
  font-size: 12px;
  color: var(--danger);
  text-decoration: underline;
}

code {
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
