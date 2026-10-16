<template>
  <div class="report">
    <p v-if="ctx.applyError" class="error-msg">{{ ctx.applyError }}</p>
    <p v-if="!report" class="empty">
      {{ ctx.applying ? 'Выполняется анонимизация…' : 'Нажмите «Анонимизировать», чтобы получить результат и отчёт.' }}
    </p>

    <template v-else>
      <div class="status" :class="`tone-${ctx.status.tone}`">
        <strong>{{ ctx.status.label }}</strong>
        <span v-if="ctx.resultStale" class="stale">
          Настройки или решения изменились после запуска — запустите анонимизацию заново.
        </span>
      </div>

      <section class="block">
        <h4>Заменено: {{ report.replaced }} знач.</h4>
        <ul class="plain">
          <li v-for="row in report.by_category" :key="row.category">
            {{ row.label }} — {{ row.count }}
          </li>
          <li v-if="report.sweep.replacements">
            Найдено «по тексту» (имена, e-mail, телефоны, номера в свободных полях): {{ report.sweep.replacements }}
            в {{ report.sweep.values_changed }} знач.
          </li>
          <li v-if="report.comments_removed">Удалено комментариев/инструкций: {{ report.comments_removed }}</li>
        </ul>
        <p class="hint">
          Режим согласованности:
          {{ consistencyLabel }}.
          <template v-if="report.llm?.used">
            ИИ ({{ report.llm.alias }}) нашёл фрагментов: {{ report.llm.entities_found }}.
          </template>
        </p>
      </section>

      <section v-if="report.unresolved_suspicious || report.unclassified.length" class="block">
        <h4>Не классифицировано: {{ report.unclassified.length }}
          <span v-if="report.unresolved_suspicious" class="warn-text">
            (подозрительных: {{ report.unresolved_suspicious }})
          </span>
        </h4>
        <p class="hint">
          Эти поля остались как есть. Разберите их на вкладке «Проверка» и повторите анонимизацию.
        </p>
        <button type="button" class="btn-secondary btn-sm" @click="$emit('open-queue')">Перейти к проверке</button>
      </section>

      <section class="block" :class="{ bad: !report.leak_check.ok }">
        <h4>
          Контроль утечек:
          <span :class="report.leak_check.ok ? 'ok-text' : 'warn-text'">
            {{ report.leak_check.ok ? 'исходные данные в «оставленных» полях не найдены' : `найдено ${report.leak_check.items.length}` }}
          </span>
        </h4>
        <ul v-if="!report.leak_check.ok" class="plain">
          <li v-for="(item, i) in report.leak_check.items" :key="i">
            <code>{{ item.path }}@{{ item.attr === '#text' ? 'текст' : item.attr }}</code>
            <button v-if="item.line" type="button" class="line-link" @click="$emit('go-to-line', item.line)">
              стр. {{ item.line }}
            </button>
            <span class="hint"> ({{ item.action === 'keep' ? 'оставлено правилом' : item.action }})</span>
          </li>
        </ul>
      </section>

      <section v-if="report.validation" class="block">
        <h4>Проверка результата</h4>
        <ul class="plain">
          <li :class="report.validation.dtd.valid_after ? 'ok-text' : 'warn-text'">
            DTD: {{ report.validation.dtd.valid_after ? 'документ валиден' : 'есть ошибки' }}
            <span v-if="report.validation.dtd.valid_before !== report.validation.dtd.valid_after" class="hint">
              (до замены: {{ report.validation.dtd.valid_before ? 'валиден' : 'ошибки' }})
            </span>
          </li>
          <li
            v-for="(e, i) in report.validation.dtd.errors_after"
            :key="`d${i}`"
            class="err"
          >
            <button v-if="e.line" type="button" class="line-link" @click="$emit('go-to-line', e.line)">стр. {{ e.line }}</button>
            {{ e.message }}
          </li>
          <li :class="report.validation.rules.new_errors.length ? 'warn-text' : 'ok-text'">
            Правила атрибутов: новых нарушений —
            {{ report.validation.rules.new_errors.length }}
          </li>
          <li v-for="(e, i) in report.validation.rules.new_errors" :key="`r${i}`" class="err">
            <button v-if="e.line" type="button" class="line-link" @click="$emit('go-to-line', e.line)">стр. {{ e.line }}</button>
            {{ e.path }}@{{ e.attr }}: {{ e.message }}
          </li>
        </ul>
      </section>

      <ul v-if="report.warnings.length" class="plain warnings">
        <li v-for="(w, i) in report.warnings" :key="i">{{ w }}</li>
      </ul>

      <div v-if="blockedByStrict" class="strict">
        <p>
          <strong>Выдача заблокирована:</strong> остались подозрительные неклассифицированные поля
          ({{ report.unresolved_suspicious }}). Скачивание и открытие в Генераторе недоступны, пока вы
          их не разберёте.
        </p>
        <label class="check">
          <input v-model="ctx.forceHandoff" type="checkbox" />
          <span>Всё равно выдать результат (я понимаю риск)</span>
        </label>
      </div>

      <section class="block actions">
        <h4>Результат</h4>
        <div class="btns">
          <button type="button" class="btn-primary btn-sm" :disabled="ctx.handoffBlocked" @click="ctx.downloadResult()">
            Скачать .xml
          </button>
          <button type="button" class="btn-secondary btn-sm" :disabled="ctx.handoffBlocked" @click="ctx.copyResult()">
            Копировать
          </button>
          <button type="button" class="btn-secondary btn-sm" :disabled="ctx.handoffBlocked" @click="openSave">
            В «Мои документы»
          </button>
          <button type="button" class="btn-secondary btn-sm" :disabled="ctx.handoffBlocked" @click="ctx.openInGenerator()">
            Открыть в Генераторе
          </button>
        </div>
        <form v-if="saveOpen" class="save" @submit.prevent="submitSave">
          <label for="anon-save-name">Имя документа</label>
          <input id="anon-save-name" v-model="saveName" type="text" required />
          <label for="anon-save-folder">Папка</label>
          <select id="anon-save-folder" v-model="saveFolder">
            <option value="">Без группы</option>
            <option v-for="f in ctx.personalFolders" :key="f" :value="f">{{ f }}</option>
          </select>
          <div class="btns">
            <button type="button" class="btn-secondary btn-sm" @click="saveOpen = false">Отмена</button>
            <button type="submit" class="btn-primary btn-sm" :disabled="!saveName.trim()">Сохранить</button>
          </div>
        </form>
        <p v-if="ctx.actionMessage" class="hint ok-text">{{ ctx.actionMessage }}</p>
        <p class="review">
          Автоматическая анонимизация не гарантирует полноты: просмотрите результат перед использованием в
          тестовой среде — в первую очередь свободный текст и нестандартные поля.
        </p>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { CONSISTENCY_MODES } from '../../utils/anonymize'

const props = defineProps({ ctx: { type: Object, required: true } })
defineEmits(['go-to-line', 'open-queue'])

const saveOpen = ref(false)
const saveName = ref('')
const saveFolder = ref('')

const report = computed(() => props.ctx.report)
const consistencyLabel = computed(
  () => CONSISTENCY_MODES.find((m) => m.id === report.value?.consistency)?.label || '',
)
const blockedByStrict = computed(
  () => !props.ctx.forceHandoff && (report.value?.unresolved_suspicious || 0) > 0,
)

function openSave() {
  saveName.value = `${props.ctx.sourceName.replace(/\.xml$/i, '') || report.value?.root_element || 'document'}-anon`
  saveFolder.value = ''
  saveOpen.value = true
}

async function submitSave() {
  const ok = await props.ctx.saveResultToLibrary({
    name: saveName.value.trim(),
    folder: saveFolder.value,
  })
  if (ok) saveOpen.value = false
}
</script>

<style scoped>
.report {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty,
.hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted);
}

.status {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  font-size: 13px;
}

.tone-success {
  border-color: color-mix(in srgb, var(--success) 45%, var(--border));
  background: color-mix(in srgb, var(--success) 10%, transparent);
  color: var(--success);
}

.tone-warning {
  border-color: color-mix(in srgb, var(--warning) 45%, var(--border));
  background: color-mix(in srgb, var(--warning) 10%, transparent);
  color: var(--warning);
}

.stale {
  font-size: 12px;
  color: var(--text);
}

.block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.block.bad {
  padding: 8px 10px;
  border-radius: var(--radius);
  border: 1px solid color-mix(in srgb, var(--warning) 45%, var(--border));
}

h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.plain {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.plain code {
  font-family: var(--font-mono);
  font-size: 11px;
}

.err {
  color: var(--danger);
}

.warnings {
  color: var(--warning);
}

.ok-text {
  color: var(--success);
}

.warn-text {
  color: var(--warning);
  font-weight: 500;
}

.strict {
  padding: 10px 12px;
  border-radius: var(--radius);
  border: 1px solid color-mix(in srgb, var(--danger) 45%, var(--border));
  background: color-mix(in srgb, var(--danger) 8%, transparent);
  font-size: 12px;
  line-height: 1.45;
}

.strict p {
  margin: 0 0 8px;
}

.check {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: var(--text);
  cursor: pointer;
}

.check input {
  width: 14px;
  min-width: 14px;
  height: 14px;
  margin: 0;
  padding: 0;
  accent-color: var(--accent);
}

.btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.btn-sm {
  padding: 5px 10px;
  font-size: 12px;
}

.save {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
}

.review {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.45;
  border-radius: var(--radius);
  background: var(--surface2);
  color: var(--text-muted);
}

.line-link {
  padding: 0;
  background: none;
  border: none;
  font-size: 11px;
  color: var(--accent);
  text-decoration: underline;
}
</style>
