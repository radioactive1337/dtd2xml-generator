<template>
  <div class="settings">
    <section class="block">
      <h3 class="block-title">Источник</h3>
      <input
        ref="fileInput"
        type="file"
        accept=".xml,text/xml,application/xml"
        class="hidden-input"
        @change="onFile"
      />
      <div class="row">
        <button type="button" class="btn-secondary btn-sm" @click="fileInput?.click()">
          Импорт .xml
        </button>
        <span v-if="ctx.sourceName" class="file-name" :title="ctx.sourceName">{{ ctx.sourceName }}</span>
        <button
          type="button"
          class="btn-secondary btn-sm btn-danger-tint"
          :disabled="!ctx.hasSource && !ctx.result"
          title="Удалить исходный XML, результат и решения из памяти страницы"
          @click="ctx.clearAll()"
        >
          Очистить всё
        </button>
      </div>
      <p class="hint">
        Или вставьте XML в правый редактор («Исходный XML»). Документ хранится только в памяти этой
        страницы — не в браузерном хранилище и не на диске сервера.
      </p>
      <p v-if="ctx.sourceError" class="error-msg">{{ ctx.sourceError }}</p>

      <label class="field-label" for="anon-schema">DTD-схема (для проверки результата)</label>
      <select id="anon-schema" v-model="ctx.schemaId">
        <option value="">Без DTD</option>
        <option v-for="s in ctx.schemas" :key="s.schema_id" :value="s.schema_id">
          {{ schemaLabel(s) }}
        </option>
      </select>
    </section>

    <section class="block">
      <h3 class="block-title">Согласованность замен</h3>
      <label v-for="mode in CONSISTENCY_MODES" :key="mode.id" class="radio">
        <input v-model="ctx.consistency" type="radio" name="anon-consistency" :value="mode.id" />
        <span>
          <span class="radio-title">{{ mode.label }}</span>
          <span class="hint">{{ mode.hint }}</span>
        </span>
      </label>
      <template v-if="ctx.consistency === 'project'">
        <label class="field-label" for="anon-seed">Seed проекта</label>
        <input
          id="anon-seed"
          v-model="ctx.seed"
          type="text"
          autocomplete="off"
          placeholder="Например: sprint-42"
        />
        <p class="hint">
          Seed — общий секрет команды: зная его, можно воспроизвести замены. Не используйте реальные
          данные в качестве seed.
        </p>
      </template>
    </section>

    <section class="block">
      <h3 class="block-title">Параметры</h3>
      <label class="check">
        <input v-model="ctx.stripComments" type="checkbox" />
        <span>Удалять комментарии и инструкции обработки (<code>&lt;!-- --&gt;</code>)</span>
      </label>
      <p v-if="!ctx.stripComments" class="hint">
        Комментарии останутся в результате; известные ПДн в них будут заменены.
      </p>

      <details class="categories">
        <summary>
          Категории ПДн для замены ({{ ctx.enabledCategories.length }} из {{ ctx.categories.length }})
        </summary>
        <div class="cat-actions">
          <button type="button" class="link" @click="ctx.setAllCategories(true)">Выбрать все</button>
          <button type="button" class="link" @click="ctx.setAllCategories(false)">Снять все</button>
        </div>
        <div v-for="group in groupedCategories" :key="group.name" class="cat-group">
          <div class="cat-group-title">{{ group.name }}</div>
          <label v-for="c in group.items" :key="c.id" class="check small">
            <input
              type="checkbox"
              :checked="ctx.enabledCategories.includes(c.id)"
              @change="ctx.toggleCategory(c.id)"
            />
            <span>{{ c.label }}</span>
          </label>
        </div>
        <p class="hint">Отключённая категория не заменяется, но поля с ней остаются в списке находок.</p>
      </details>
    </section>

    <section class="block ai-block">
      <h3 class="block-title">ИИ-помощник</h3>
      <label class="check" :class="{ disabled: !ctx.llmAvailable }">
        <input v-model="ctx.useLlm" type="checkbox" :disabled="!ctx.llmAvailable" />
        <span>Искать ПДн в свободном тексте с помощью ИИ</span>
      </label>
      <p v-if="!ctx.llmAvailable" class="hint">
        Нет настроенных LLM-алиасов — добавьте их в «Настройках».
      </p>
      <template v-else>
        <select v-model="ctx.llmAlias" :disabled="!ctx.useLlm" aria-label="LLM-алиас">
          <option v-for="a in ctx.llmAliases" :key="a" :value="a">{{ a }}</option>
        </select>
        <p class="warn">
          При включении тексты свободных полей и описания неизвестных полей уходят во внутренний
          LLM-алиас <strong>с реальными значениями</strong>. ИИ лишь указывает, какие фрагменты
          являются ПДн; саму замену выполняет код.
        </p>
      </template>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { CONSISTENCY_MODES, groupCategoriesByGroup } from '../../utils/anonymize'
import { schemaFileName } from '../../utils/dtdSchema'

const props = defineProps({ ctx: { type: Object, required: true } })

const fileInput = ref(null)
const groupedCategories = computed(() => groupCategoriesByGroup(props.ctx.categories))

function schemaLabel(schema) {
  return schemaFileName(schema)
}

async function onFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) await props.ctx.importFile(file)
}
</script>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.block-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.hidden-input {
  display: none;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.file-name {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}

.btn-danger-tint {
  margin-left: auto;
  color: var(--danger);
}

.hint {
  display: block;
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted);
}

.warn {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.45;
  border-radius: var(--radius);
  border: 1px solid color-mix(in srgb, var(--warning) 40%, var(--border));
  background: color-mix(in srgb, var(--warning) 10%, transparent);
  color: var(--text);
}

.field-label {
  margin-top: 4px;
}

.radio,
.check {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
}

.check.small {
  font-size: 12px;
  margin: 2px 0;
}

.check.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.radio input,
.check input {
  width: 14px;
  min-width: 14px;
  height: 14px;
  margin: 3px 0 0;
  padding: 0;
  accent-color: var(--accent);
}

.radio-title {
  display: block;
  font-weight: 500;
}

.categories {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 10px;
  background: var(--surface2);
}

.categories summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
}

.cat-actions {
  display: flex;
  gap: 12px;
  margin: 8px 0 4px;
}

.link {
  padding: 0;
  background: none;
  border: none;
  font-size: 12px;
  color: var(--accent);
  text-decoration: underline;
}

.cat-group {
  margin-top: 8px;
}

.cat-group-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

code {
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
