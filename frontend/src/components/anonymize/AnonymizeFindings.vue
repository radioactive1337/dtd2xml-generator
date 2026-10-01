<template>
  <div class="findings">
    <p v-if="!ctx.analysis" class="empty">
      {{ ctx.analyzing ? 'Анализ документа…' : 'Загрузите XML — здесь появятся найденные ПДн.' }}
    </p>
    <template v-else>
      <p class="summary">
        К замене: <strong>{{ ctx.analysis.stats.replace }}</strong> знач.
        <span v-if="ctx.analysis.stats.disabled">
          · категория отключена: {{ ctx.analysis.stats.disabled }}
        </span>
        · оставлено: {{ ctx.analysis.stats.keep + ctx.analysis.stats.skip }}
        · не классифицировано: {{ ctx.analysis.stats.unclassified }}
      </p>
      <p v-if="ctx.analysis.findings_truncated" class="hint">
        Показана только часть находок; замена будет применена ко всем.
      </p>
      <p v-if="!groups.length" class="empty">ПДн по правилам не найдено.</p>

      <details v-for="group in groups" :key="group.category" class="group" :open="groups.length <= 3">
        <summary>
          <span class="group-title">{{ group.label }}</span>
          <span class="badge">{{ group.count }}</span>
        </summary>
        <ul class="fields">
          <li v-for="field in group.fields" :key="field.key" class="field">
            <div class="field-main">
              <code class="field-name" :title="field.key">{{ fieldLabel(field) }}</code>
              <span class="badge muted">×{{ field.count }}</span>
              <span class="source" :title="sourceTitle(field.source)">{{ sourceLabel(field.source) }}</span>
            </div>
            <div class="field-meta">
              <span v-if="field.previews.length" class="preview">{{ field.previews.join(' · ') }}</span>
              <span v-if="field.lines.length" class="lines">
                стр.
                <button
                  v-for="line in field.lines"
                  :key="line"
                  type="button"
                  class="line-link"
                  @click="$emit('go-to-line', line)"
                >
                  {{ line }}
                </button>
              </span>
            </div>
            <div class="field-actions">
              <template v-if="field.action === 'disabled'">
                <span class="hint">категория отключена в настройках</span>
              </template>
              <template v-else-if="isKept(field.key)">
                <span class="hint">не заменяется в этом документе</span>
                <button type="button" class="link" @click="ctx.undoDecision(field.key)">Отменить</button>
              </template>
              <template v-else>
                <button type="button" class="link" @click="ctx.decide(field.key, 'keep')">
                  Не заменять здесь
                </button>
                <button type="button" class="link" @click="rememberKeep(field)">
                  Запомнить: не ПДн
                </button>
              </template>
            </div>
          </li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fieldLabel, groupFindingsByCategory } from '../../utils/anonymize'

const props = defineProps({ ctx: { type: Object, required: true } })
defineEmits(['go-to-line'])

const groups = computed(() => groupFindingsByCategory(props.ctx.analysis?.findings || []))

const SOURCE_LABELS = {
  rule: 'правило',
  manual: 'ваше правило',
  builtin: 'встроено',
  heuristic: 'эвристика',
  llm_suggested: 'ИИ',
  override: 'решение',
}

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source || 'правило'
}

function sourceTitle(source) {
  if (source === 'heuristic' || source === 'builtin') {
    return 'Определено автоматически по имени/значению поля, правила нет'
  }
  return 'Откуда взято решение о замене'
}

function isKept(key) {
  return props.ctx.overrides[key]?.action === 'keep'
}

function rememberKeep(field) {
  return props.ctx.remember(
    { key: field.key, element: field.element, attr: field.attr, name: field.name },
    'exact',
    'keep',
  )
}
</script>

<style scoped>
.findings {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty,
.hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.summary {
  margin: 0;
  font-size: 13px;
}

.group {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
  padding: 6px 10px;
}

.group summary {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
}

.group-title {
  flex: 1;
  font-weight: 500;
}

.badge {
  padding: 1px 7px;
  font-size: 11px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
}

.badge.muted {
  background: var(--border);
  color: var(--text-muted);
}

.fields {
  list-style: none;
  margin: 8px 0 2px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field {
  padding-top: 8px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.field-main,
.field-meta,
.field-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.field-name {
  font-family: var(--font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.source {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}

.preview {
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
</style>
