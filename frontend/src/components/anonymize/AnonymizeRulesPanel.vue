<template>
  <div class="rules">
    <p class="hint">
      Правила определяют, какие поля считать ПДн. Сначала добавьте правило в свои — формой ниже или
      «Запомнить как правило» на вкладке «Проверка». Когда оно проверено, перенесите его в общие:
      запись попадёт в <code>config/anonymize_rules.json</code> и будет действовать для всей команды.
      Личные правила дополняют общие и при равной точности их перекрывают.
    </p>

    <details ref="formBox" class="editor">
      <summary>{{ editingId ? 'Изменить правило' : 'Добавить правило' }}</summary>
      <p class="hint editor-hint">
        Правило сохраняется в ваши личные. В общие его можно перенести отдельной кнопкой у строки.
      </p>
      <form class="editor-grid" @submit.prevent="submitForm">
        <label>
          Атрибут
          <input v-model="form.attr" required placeholder="value, inn, passport*" autocomplete="off" />
        </label>
        <label>
          Элемент
          <input v-model="form.element" placeholder="необязательно, cs:attribute" autocomplete="off" />
        </label>
        <label>
          name
          <input v-model="form.name" placeholder="для cs:*, например LastName" autocomplete="off" />
        </label>
        <label>
          Действие
          <select v-model="form.action">
            <option value="replace">Заменить (это ПДн)</option>
            <option value="keep">Оставить (не ПДн)</option>
          </select>
        </label>
        <label v-if="form.action === 'replace'" class="span-2">
          Категория
          <select v-model="form.category" required>
            <option value="">Категория…</option>
            <optgroup v-for="group in groupedCategories" :key="group.name" :label="group.name">
              <option v-for="c in group.items" :key="c.id" :value="c.id">{{ c.label }}</option>
            </optgroup>
          </select>
        </label>
        <label class="span-2">
          Заметка
          <input v-model="form.note" placeholder="необязательно" autocomplete="off" />
        </label>
        <div class="span-2">
          <details ref="parentBox" class="nested">
            <summary>Уточнение по родителю</summary>
            <div class="editor-grid nested-grid">
              <label>
                Элемент родителя
                <input v-model="form.parent_element" placeholder="address" autocomplete="off" />
              </label>
              <label>
                name родителя
                <input v-model="form.parent_name" placeholder="Passport" autocomplete="off" />
              </label>
              <label class="span-2">
                value родителя
                <input v-model="form.parent_value" placeholder="Phone" autocomplete="off" />
              </label>
            </div>
          </details>
        </div>
        <div class="editor-actions span-2">
          <button type="submit" class="btn-primary btn-sm" :disabled="saving || !canSave">
            {{ saving ? 'Сохранение…' : editingId ? 'Сохранить в мои' : 'Добавить в мои' }}
          </button>
          <button v-if="editingId" type="button" class="btn-secondary btn-sm" :disabled="saving" @click="resetForm">
            Отмена
          </button>
        </div>
      </form>
      <p v-if="formError" class="error-msg">{{ formError }}</p>
    </details>

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
          <span class="rule-actions">
            <template v-if="rule.layer === 'user'">
              <button type="button" class="link" :disabled="actingId === rule.id" @click="startEdit(rule)">
                Изменить
              </button>
              <button
                type="button"
                class="link promote"
                :disabled="actingId === rule.id"
                title="Записать в общие правила команды и убрать личную копию"
                @click="confirmPromote(rule)"
              >
                В общие
              </button>
            </template>
            <button
              v-else
              type="button"
              class="link"
              :disabled="actingId === rule.id"
              title="Скопировать в свои правила, чтобы поправить и затем снова перенести в общие"
              @click="copyToUser(rule)"
            >
              В мои
            </button>
            <button type="button" class="link remove" :disabled="actingId === rule.id" @click="confirmRemove(rule)">
              Удалить
            </button>
          </span>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  emptyRuleForm,
  formToRule,
  groupCategoriesByGroup,
  ruleKey,
  ruleSummary,
  ruleToForm,
} from '../../utils/anonymize'

const props = defineProps({ ctx: { type: Object, required: true } })

const r = computed(() => props.ctx.rules)
const fileInput = ref(null)
const replaceOnImport = ref(false)
const form = ref(emptyRuleForm())
const editingId = ref('')
const editingKey = ref('')
const saving = ref(false)
const actingId = ref('')
const formError = ref('')
const formBox = ref(null)
const parentBox = ref(null)

const categoryById = computed(() => new Map(props.ctx.categories.map((c) => [c.id, c.label])))
const groupedCategories = computed(() => groupCategoriesByGroup(props.ctx.categories))
const canSave = computed(
  () => form.value.attr.trim() && (form.value.action !== 'replace' || form.value.category),
)

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

function resetForm() {
  form.value = emptyRuleForm()
  editingId.value = ''
  editingKey.value = ''
  formError.value = ''
  if (parentBox.value) parentBox.value.open = false
}

function startEdit(rule) {
  form.value = ruleToForm(rule)
  editingId.value = rule.id
  editingKey.value = ruleKey(rule)
  formError.value = ''
  if (formBox.value) formBox.value.open = true
  if (parentBox.value) {
    parentBox.value.open = Boolean(rule.parent_element || rule.parent_name || rule.parent_value)
  }
  formBox.value?.scrollIntoView({ block: 'nearest' })
}

async function submitForm() {
  const rule = formToRule(form.value)
  if (!rule.attr) {
    formError.value = 'Укажите атрибут'
    return
  }
  if (rule.action === 'replace' && !rule.category) {
    formError.value = 'Выберите категорию'
    return
  }
  formError.value = ''
  const previousId = editingId.value
  const previousKey = editingKey.value
  saving.value = true
  const ok = await r.value.addRules([rule], {
    successMessage: previousId ? 'Правило сохранено в ваших' : 'Правило добавлено в ваши',
  })
  saving.value = false
  if (!ok) return
  if (previousId && ruleKey(rule) !== previousKey) await r.value.remove(previousId)
  resetForm()
}

function confirmPromote(rule) {
  const stored = r.value.globalRules
  const globals = Array.isArray(stored) ? stored : (stored?.value ?? [])
  const clash = globals.some((item) => ruleKey(item) === ruleKey(rule))
  const clashNote = clash ? ' Общее правило с той же областью будет заменено.' : ''
  const text =
    'Сделать правило общим для всех? Оно запишется в config/anonymize_rules.json и исчезнет из ваших личных.' +
    clashNote
  if (!window.confirm(text)) return
  actingId.value = rule.id
  r.value.promote(rule.id).finally(() => {
    if (actingId.value === rule.id) actingId.value = ''
  })
}

function confirmRemove(rule) {
  if (rule.layer === 'global') {
    if (!window.confirm('Удалить общее правило? Оно пропадёт у всех пользователей.')) return
    actingId.value = rule.id
    r.value.removeGlobal(rule.id).finally(() => {
      if (actingId.value === rule.id) actingId.value = ''
    })
    return
  }
  r.value.remove(rule.id)
}

async function copyToUser(rule) {
  actingId.value = rule.id
  await r.value.addRules([formToRule(ruleToForm(rule))], {
    successMessage: 'Скопировано в ваши правила. Поправьте при необходимости и нажмите «В общие».',
  })
  if (actingId.value === rule.id) actingId.value = ''
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

.rule-actions {
  margin-left: auto;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.link {
  padding: 0;
  background: none;
  border: none;
  font-size: 12px;
  color: var(--accent);
  text-decoration: underline;
}

.link:disabled {
  opacity: 0.5;
  cursor: default;
}

.link.remove {
  color: var(--danger);
}

.editor {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 10px;
  background: var(--surface);
}

.editor summary,
.nested summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.editor-hint {
  margin-top: 8px;
}

.editor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px 10px;
  margin-top: 8px;
}

.editor-grid label {
  margin: 0;
}

.span-2 {
  grid-column: 1 / -1;
}

.nested {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 10px;
  background: var(--surface2);
}

.nested summary {
  font-weight: 500;
  font-size: 12px;
}

.nested-grid {
  margin-top: 8px;
}

.editor-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.error-msg {
  margin: 8px 0 0;
}

code {
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
