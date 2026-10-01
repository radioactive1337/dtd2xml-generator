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
        Для этих полей нет правила. Подозрительные (похожие на данные) блокируют выдачу результата, пока
        вы не примете решение.
      </p>

      <div class="bulk">
        <label class="check">
          <input type="checkbox" :checked="allSelected" @change="toggleAll($event.target.checked)" />
          <span>Выбрано: {{ selected.size }}</span>
        </label>
        <select v-model="bulkCategory" class="mini" aria-label="Категория для выбранных">
          <option value="">Категория…</option>
          <option v-for="c in ctx.categories" :key="c.id" :value="c.id">{{ c.label }}</option>
        </select>
        <button type="button" class="btn-secondary btn-sm" :disabled="!selected.size || !bulkCategory" @click="bulkReplace">
          Это ПДн
        </button>
        <button type="button" class="btn-secondary btn-sm" :disabled="!selected.size" @click="bulk('keep')">
          Не ПДн
        </button>
        <button type="button" class="btn-secondary btn-sm" :disabled="!selected.size" @click="bulk('skip')">
          Пропустить
        </button>
        <button type="button" class="btn-secondary btn-sm" :disabled="!acceptableCount" @click="acceptSuggestions">
          Принять подсказки ({{ acceptableCount }})
        </button>
      </div>
      <label class="check bulk-remember">
        <input v-model="bulkRemember" type="checkbox" />
        <span>Запоминать групповые решения как правила (для точного поля)</span>
      </label>

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
          <div v-if="item.suggested_category || item.ai_category" class="suggest">
            <button
              v-if="item.suggested_category"
              type="button"
              class="chip"
              :title="item.hint || 'Подсказка эвристики'"
              @click="choose(item, item.suggested_category)"
            >
              Эвристика: {{ categoryLabel(item.suggested_category) }}
            </button>
            <button
              v-if="item.ai_category"
              type="button"
              class="chip ai"
              title="Предложение ИИ — проверьте перед применением"
              @click="item.ai_category === 'none' ? apply(item, 'keep') : choose(item, item.ai_category)"
            >
              ИИ: {{ item.ai_category === 'none' ? 'не ПДн' : categoryLabel(item.ai_category) }}
            </button>
          </div>

          <div class="decide">
            <select v-model="picked[item.key]" class="mini" :aria-label="`Категория для ${fieldLabel(item)}`">
              <option :value="undefined">Категория…</option>
              <option v-for="c in ctx.categories" :key="c.id" :value="c.id">{{ c.label }}</option>
            </select>
            <button
              type="button"
              class="btn-primary btn-sm"
              :disabled="!(picked[item.key] || item.suggested_category)"
              @click="apply(item, 'replace', picked[item.key] || item.suggested_category)"
            >
              Это ПДн
            </button>
            <button type="button" class="btn-secondary btn-sm" @click="apply(item, 'keep')">Не ПДн, оставить</button>
            <button type="button" class="btn-secondary btn-sm" @click="apply(item, 'skip')" title="Не менять в этом документе, правило не создаётся">
              Пропустить здесь
            </button>
          </div>
          <div class="remember">
            <label class="check">
              <input v-model="remember[item.key]" type="checkbox" />
              <span>Запомнить как правило</span>
            </label>
            <select
              v-if="remember[item.key]"
              v-model="scopes[item.key]"
              class="mini scope"
              :aria-label="`Область правила для ${fieldLabel(item)}`"
            >
              <option v-for="s in ruleScopeOptions(item)" :key="s.id" :value="s.id">{{ s.label }}</option>
            </select>
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
import { computed, reactive, ref } from 'vue'
import { fieldLabel, ruleScopeOptions } from '../../utils/anonymize'

const props = defineProps({ ctx: { type: Object, required: true } })
defineEmits(['go-to-line'])

const picked = reactive({})
const remember = reactive({})
const scopes = reactive({})
const selected = ref(new Set())
const bulkCategory = ref('')
const bulkRemember = ref(false)

const items = computed(() => props.ctx.queue)
const allSelected = computed(() => items.value.length > 0 && selected.value.size === items.value.length)
const decided = computed(() => Object.entries(props.ctx.overrides))
const categoryById = computed(() => new Map(props.ctx.categories.map((c) => [c.id, c.label])))

const acceptableCount = computed(
  () => items.value.filter((i) => selected.value.has(i.key) && (i.ai_category || i.suggested_category)).length,
)

function categoryLabel(id) {
  return categoryById.value.get(id) || id
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
}

function toggleAll(on) {
  selected.value = on ? new Set(items.value.map((i) => i.key)) : new Set()
}

function choose(item, category) {
  picked[item.key] = category
}

async function apply(item, action, category = null) {
  if (remember[item.key] && action !== 'skip') {
    await props.ctx.remember(item, scopes[item.key] || 'exact', action, category)
  } else {
    props.ctx.decide(item.key, action, category)
  }
}

function selectedItems() {
  return items.value.filter((i) => selected.value.has(i.key))
}

async function bulk(action, category = null) {
  const list = selectedItems()
  if (!list.length) return
  if (bulkRemember.value && action !== 'skip') {
    await props.ctx.rememberMany(list, 'exact', action, category)
  } else {
    props.ctx.decideMany(list.map((i) => i.key), action, category)
  }
  selected.value = new Set()
}

function bulkReplace() {
  return bulk('replace', bulkCategory.value)
}

async function acceptSuggestions() {
  const list = selectedItems().filter((i) => i.ai_category || i.suggested_category)
  for (const item of list) {
    const category = item.suggested_category || item.ai_category
    if (category === 'none') {
      props.ctx.decide(item.key, 'keep')
    } else if (bulkRemember.value) {
      await props.ctx.remember(item, 'exact', 'replace', category)
    } else {
      props.ctx.decide(item.key, 'replace', category)
    }
  }
  selected.value = new Set()
}
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
.remember,
.meta,
.suggest,
.item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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
  max-width: 190px;
  padding: 4px 8px;
  font-size: 12px;
}

.mini.scope {
  max-width: 100%;
  flex: 1;
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
  gap: 10px;
}

.item {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
  display: flex;
  flex-direction: column;
  gap: 6px;
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

.chip {
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
}

.chip.ai {
  background: color-mix(in srgb, var(--llm-accent) 14%, transparent);
  color: var(--llm-accent);
  border-color: color-mix(in srgb, var(--llm-accent) 35%, var(--border));
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
