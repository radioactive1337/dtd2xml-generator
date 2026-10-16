<template>
  <div class="queue">
    <div v-if="ctx.llmAvailable" class="ai-bar">
      <button
        type="button"
        class="btn-secondary btn-sm"
        :disabled="!items.length || ctx.suggesting"
        title="ИИ предложит категорию для неклассифицированных полей (по названию поля и маске значения)"
        @click="ctx.suggestForQueue()"
      >
        Предложить категории (ИИ)
      </button>
      <button
        type="button"
        class="btn-secondary btn-sm"
        :disabled="!ctx.schemaId || ctx.suggesting"
        title="Заранее классифицировать поля всей DTD по их названиям и документации (без значений)"
        @click="ctx.suggestForSchema()"
      >
        Классифицировать всю DTD
      </button>
      <button v-if="ctx.suggesting" type="button" class="link" @click="ctx.cancelSuggest()">Остановить</button>
      <span v-if="ctx.suggesting" class="hint">Работает ИИ…</span>
      <span v-else-if="ctx.suggestProgress" class="hint">{{ ctx.suggestProgress }}</span>
    </div>
    <p v-if="ctx.suggestError" class="error-msg">{{ ctx.suggestError }}</p>

    <p v-if="!ctx.analysis" class="empty">
      {{ ctx.analyzing ? 'Анализ документа…' : 'Загрузите XML, чтобы увидеть неклассифицированные поля.' }}
    </p>
    <p v-else-if="!items.length" class="empty ok">Неклассифицированных полей нет.</p>

    <template v-if="items.length">
      <p class="hint">
        Подозрительные поля блокируют выдачу, пока по ним нет решения. Подсказка уже стоит в списке
        категории — отдельная кнопка для неё не нужна.
      </p>

      <div class="bulk">
        <label class="check">
          <input type="checkbox" :checked="allSelected" @change="toggleAll($event.target.checked)" />
          <span>Выбрано: {{ selected.size }}</span>
        </label>
        <select v-model="bulkCategory" class="mini" aria-label="Общая категория для выбранных">
          <option value="">Подсказка каждого поля</option>
          <optgroup v-for="group in groupedCategories" :key="group.name" :label="group.name">
            <option v-for="c in group.items" :key="c.id" :value="c.id">{{ c.label }}</option>
          </optgroup>
        </select>
        <button
          type="button"
          class="btn-primary btn-sm"
          :disabled="!replaceCount"
          :title="bulkReplaceTitle"
          @click="bulkReplace"
        >
          Это ПДн{{ selected.size ? ` (${replaceCount})` : '' }}
        </button>
        <button type="button" class="btn-secondary btn-sm" :disabled="!selected.size" @click="bulk('keep')">
          Не ПДн
        </button>
        <button type="button" class="btn-secondary btn-sm" :disabled="!selected.size" title="Не менять в этом документе, правило не создаётся" @click="bulk('skip')">
          Пропустить
        </button>
      </div>
      <div class="bulk remember-row">
        <label class="check">
          <input v-model="rememberAll" type="checkbox" />
          <span>Запомнить как правила</span>
        </label>
        <select
          v-if="rememberAll"
          v-model="rememberScope"
          class="mini"
          aria-label="Область запоминаемых правил"
          title="Для поля без name или без атрибута область сужается до «только это поле»"
        >
          <option v-for="option in SCOPE_OPTIONS" :key="option.id" :value="option.id">{{ option.label }}</option>
        </select>
      </div>
      <p v-if="bulkNote" class="hint">{{ bulkNote }}</p>

      <ul class="items">
        <li v-for="item in items" :key="item.key" class="item" :class="{ suspicious: item.suspicious }">
          <div class="item-head">
            <input
              type="checkbox"
              :checked="selected.has(item.key)"
              :aria-label="`Выбрать ${fieldLabel(item)}`"
              @change="toggle(item.key, $event.target.checked)"
            />
            <code class="item-name" :title="item.key">{{ fieldLabel(item) }}</code>
            <span class="badge">×{{ item.count }}</span>
            <span v-if="item.suspicious" class="badge warn" title="Значение похоже на данные">подозрительно</span>
          </div>
          <p v-if="item.doc" class="doc">{{ item.doc }}</p>
          <div class="meta">
            <span v-if="item.samples.length" class="sample" title="Значение замаскировано">{{ item.samples.join(' · ') }}</span>
            <span v-if="item.lines.length" class="lines">
              стр.
              <button v-for="line in item.lines" :key="line" type="button" class="line-link" @click="$emit('go-to-line', line)">
                {{ line }}
              </button>
            </span>
          </div>
          <p v-if="hintText(item)" class="hint">{{ hintText(item) }}</p>

          <div class="decide">
            <select
              class="mini"
              :value="categoryOf(item)"
              :aria-label="`Категория для ${fieldLabel(item)}`"
              @change="picked[item.key] = $event.target.value"
            >
              <option value="">Категория…</option>
              <optgroup v-for="group in groupedCategories" :key="group.name" :label="group.name">
                <option v-for="c in group.items" :key="c.id" :value="c.id">{{ c.label }}</option>
              </optgroup>
            </select>
            <button
              type="button"
              class="btn-primary btn-sm"
              :disabled="!categoryOf(item)"
              :title="categoryOf(item) ? `Заменить как «${categoryLabel(categoryOf(item))}»` : 'Выберите категорию'"
              @click="apply(item, 'replace', categoryOf(item))"
            >
              Это ПДн
            </button>
            <button type="button" class="btn-secondary btn-sm" @click="apply(item, 'keep')">Не ПДн</button>
            <button type="button" class="btn-secondary btn-sm" title="Не менять в этом документе, правило не создаётся" @click="apply(item, 'skip')">
              Пропустить
            </button>
          </div>
        </li>
      </ul>
    </template>

    <div v-if="decided.length" class="decided">
      <div class="decided-title">Решения в этом документе ({{ decided.length }})</div>
      <ul>
        <li v-for="[key, d] in decided" :key="key">
          <code :title="key">{{ key }}</code>
          <span class="hint">{{ decisionLabel(d) }}</span>
          <button type="button" class="link" @click="ctx.undoDecision(key)">Отменить</button>
        </li>
      </ul>
      <p class="hint">Решения без «запомнить» действуют только на этот документ и не сохраняются.</p>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { effectiveCategory, fieldLabel, groupCategoriesByGroup, planBulkReplace, TEXT_ATTR } from '../../utils/anonymize'

const props = defineProps({ ctx: { type: Object, required: true } })
defineEmits(['go-to-line'])

const SCOPE_OPTIONS = [
  { id: 'exact', label: 'Только это поле' },
  { id: 'attr', label: 'Любой элемент с таким атрибутом' },
  { id: 'name', label: 'Любой элемент с таким name' },
]

const picked = reactive({})
const selected = ref(new Set())
const bulkCategory = ref('')
const rememberAll = ref(false)
const rememberScope = ref('exact')
const bulkNote = ref('')

const items = computed(() => props.ctx.queue)
const allSelected = computed(() => items.value.length > 0 && selected.value.size === items.value.length)
const decided = computed(() => Object.entries(props.ctx.overrides))
const categoryById = computed(() => new Map(props.ctx.categories.map((c) => [c.id, c.label])))
const groupedCategories = computed(() => groupCategoriesByGroup(props.ctx.categories))

const replacePlan = computed(() => {
  const chosen = {}
  for (const item of selectedItems()) {
    if (Object.prototype.hasOwnProperty.call(picked, item.key)) chosen[item.key] = picked[item.key]
  }
  return planBulkReplace(selectedItems(), { commonCategory: bulkCategory.value, picked: chosen })
})
const replaceCount = computed(() => replacePlan.value.ready.length)

const bulkReplaceTitle = computed(() => {
  if (!selected.value.size) return 'Отметьте поля галочками'
  if (!replaceCount.value) return 'У отмеченных полей нет подсказки — выберите общую категорию'
  if (!bulkCategory.value && replacePlan.value.skipped.length) {
    return `${replacePlan.value.skipped.length} без подсказки будут пропущены — для них выберите общую категорию`
  }
  if (!bulkCategory.value) return 'Каждому отмеченному полю — его подсказка'
  return 'Одна категория для всех отмеченных'
})

function categoryLabel(id) {
  return categoryById.value.get(id) || id
}

function categoryOf(item) {
  const choice = Object.prototype.hasOwnProperty.call(picked, item.key) ? picked[item.key] : undefined
  return effectiveCategory(item, choice)
}

function hintText(item) {
  const ai = item.ai_category
  const heuristic = item.suggested_category
  if (ai && ai !== 'none' && heuristic && ai !== heuristic) {
    return `Эвристика: ${categoryLabel(heuristic)}. ИИ: ${categoryLabel(ai)} — в списке стоит вариант ИИ.`
  }
  if (ai === 'none') {
    return heuristic
      ? `ИИ: не ПДн. Эвристика предлагает «${categoryLabel(heuristic)}».`
      : 'ИИ: не ПДн.'
  }
  return ''
}

function decisionLabel(d) {
  if (d.action === 'replace') return `заменить: ${categoryLabel(d.category)}`
  if (d.action === 'keep') return 'не ПДн, оставить'
  return 'пропустить'
}

function toggle(key, on) {
  const next = new Set(selected.value)
  if (on) next.add(key)
  else next.delete(key)
  selected.value = next
  bulkNote.value = ''
}

function toggleAll(on) {
  selected.value = on ? new Set(items.value.map((i) => i.key)) : new Set()
  bulkNote.value = ''
}

function selectedItems() {
  return items.value.filter((i) => selected.value.has(i.key))
}

function scopeFor(item) {
  if (rememberScope.value === 'name' && item.name) return 'name'
  if (rememberScope.value === 'attr' && item.attr !== TEXT_ATTR && item.element) return 'attr'
  return 'exact'
}

async function commit(entries) {
  if (!entries.length) return false
  if (rememberAll.value) {
    return props.ctx.rememberDecisions(
      entries.map((entry) => ({
        item: entry.item,
        scope: scopeFor(entry.item),
        action: entry.action,
        category: entry.category,
      })),
    )
  }
  props.ctx.decideEach(entries.map((entry) => ({ key: entry.item.key, action: entry.action, category: entry.category })))
  return true
}

async function apply(item, action, category = null) {
  bulkNote.value = ''
  await commit([{ item, action, category }])
}

async function bulk(action, category = null) {
  const list = selectedItems()
  if (!list.length) return
  bulkNote.value = ''
  const ok = await commit(list.map((item) => ({ item, action, category })))
  if (ok) selected.value = new Set()
}

async function bulkReplace() {
  const list = selectedItems()
  const plan = replacePlan.value
  const byKey = new Map(list.map((item) => [item.key, item]))
  const entries = plan.ready.map((row) => ({
    item: byKey.get(row.key),
    action: 'replace',
    category: row.category,
  }))
  const ok = await commit(entries)
  if (!ok) return
  selected.value = new Set(plan.skipped)
  bulkNote.value = plan.skipped.length
    ? `Без подсказки осталось ${plan.skipped.length} — выберите общую категорию.`
    : ''
}

watch(items, (list) => {
  const keys = new Set(list.map((item) => item.key))
  const next = new Set([...selected.value].filter((key) => keys.has(key)))
  if (next.size !== selected.value.size) selected.value = next
})
</script>

<style scoped>
.queue {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ai-bar,
.bulk,
.decide,
.meta,
.item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.remember-row {
  margin-top: -4px;
}

.empty,
.hint,
.doc {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted);
}

.empty.ok {
  color: var(--success);
}

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}

.mini {
  width: auto;
  max-width: 220px;
  padding: 4px 8px;
  font-size: 12px;
}

.check {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
}

.check input,
.item-head input {
  width: 14px;
  min-width: 14px;
  height: 14px;
  margin: 0;
  padding: 0;
  accent-color: var(--accent);
}

.items,
.decided ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item.suspicious {
  border-color: color-mix(in srgb, var(--warning) 55%, var(--border));
}

.item-name {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.badge {
  padding: 1px 7px;
  font-size: 11px;
  border-radius: 10px;
  background: var(--border);
  color: var(--text-muted);
}

.badge.warn {
  background: color-mix(in srgb, var(--warning) 20%, transparent);
  color: var(--warning);
}

.sample {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.lines {
  font-size: 11px;
  color: var(--text-muted);
}

.line-link,
.link {
  padding: 0;
  background: none;
  border: none;
  font-size: 11px;
  color: var(--accent);
  text-decoration: underline;
}

.link {
  font-size: 12px;
}

.line-link + .line-link {
  margin-left: 4px;
}

.decided {
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.decided-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}

.decided li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.decided code {
  font-family: var(--font-mono);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 55%;
}
</style>
