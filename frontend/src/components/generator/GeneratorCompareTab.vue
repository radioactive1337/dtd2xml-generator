<template>
  <div class="tab-pane">
    <div class="compare-toolbar">
      <button
        type="button"
        class="btn-primary btn-sm"
        :disabled="comparing"
        @click="$emit('run-compare')"
      >
        {{ comparing ? 'Проверяем…' : 'Проверить уникальность' }}
      </button>
      <span class="compare-hint">
        Сравнение структуры текущего XML со всеми эталонами того же корневого элемента.
      </span>
    </div>

    <p v-if="compareError" class="error-msg">{{ compareError }}</p>

    <template v-if="report">
      <div v-if="!report.has_references" class="results-status results-status--warn" role="status">
        <span class="results-status-dot" aria-hidden="true" />
        <span>
          Эталонов для корневого элемента «{{ report.root_element }}» не найдено — сравнивать не с чем.
        </span>
      </div>

      <template v-else>
        <div
          class="results-status"
          :class="report.is_unique ? 'results-status--warn' : 'results-status--ok'"
          role="status"
        >
          <span class="results-status-dot" aria-hidden="true" />
          <span>
            {{
              report.is_unique
                ? `Уникален по структуре: ${uniquePathsLabel}`
                : 'Совпадает по структуре с эталонами'
            }}
          </span>
        </div>

        <p class="compare-meta">
          Сравнили с {{ referencesLabel }}.
          <template v-if="report.closest">
            Ближайший эталон:
            <span class="closest-title">{{ report.closest.title || report.closest.doc_id }}</span>
            — {{ formatScore(report.closest.score) }}
          </template>
        </p>

        <section v-if="report.unique_paths?.length" class="paths-section">
          <h3 class="section-title">Уникальные пути</h3>
          <ul class="paths-list">
            <li v-for="range in rangesByPath" :key="range.key" class="path-item">
              <button
                type="button"
                class="path-link"
                :title="`Перейти к строке ${range.start_line}`"
                @click="$emit('go-to-path', range)"
              >
                <span class="path-text">{{ range.path }}</span>
                <span class="path-line">строка {{ range.start_line }}</span>
              </button>
            </li>
            <li v-for="path in pathsWithoutRange" :key="path" class="path-item">
              <span class="path-text path-text--plain">{{ path }}</span>
            </li>
          </ul>
        </section>

        <section class="ai-section">
          <div class="ai-header">
            <button
              type="button"
              class="btn-secondary btn-sm"
              :disabled="!hasUniquePaths || aiLoading || !aiAvailable"
              :title="aiButtonTitle"
              @click="$emit('run-explain')"
            >
              {{ aiLoading ? 'ИИ думает…' : 'Объяснить расхождения (ИИ)' }}
            </button>
          </div>
          <p v-if="aiError" class="error-msg">{{ aiError }}</p>
          <div v-if="aiExplanation" class="ai-output">{{ aiExplanation }}</div>
        </section>
      </template>
    </template>

    <p v-else-if="!compareError" class="compare-placeholder">
      Нажмите «Проверить уникальность», чтобы сравнить структуру XML с эталонами.
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  report: { type: Object, default: null },
  comparing: { type: Boolean, default: false },
  compareError: { type: String, default: '' },
  hasUniquePaths: { type: Boolean, default: false },
  aiAvailable: { type: Boolean, default: true },
  aiExplanation: { type: String, default: '' },
  aiLoading: { type: Boolean, default: false },
  aiError: { type: String, default: '' },
})

defineEmits(['run-compare', 'run-explain', 'go-to-path'])

const uniquePathsLabel = computed(() => {
  const count = props.report?.unique_paths?.length ?? 0
  return `${count} ${plural(count, 'новый путь', 'новых пути', 'новых путей')}`
})

const referencesLabel = computed(() => {
  const count = props.report?.references_count ?? 0
  return `${count} ${plural(count, 'эталоном', 'эталонами', 'эталонами')}`
})

const rangesByPath = computed(() =>
  (props.report?.highlight_ranges || []).map((r, i) => ({ ...r, key: `${r.path}-${i}` })),
)

const pathsWithoutRange = computed(() => {
  const covered = new Set((props.report?.highlight_ranges || []).map((r) => r.path))
  return (props.report?.unique_paths || []).filter((p) => !covered.has(p))
})

const aiButtonTitle = computed(() => {
  if (!props.aiAvailable) return 'LLM не настроен в подключениях'
  if (!props.hasUniquePaths) return 'Нет уникальных путей для объяснения'
  return 'Отправить отчёт в ИИ для объяснения'
})

function formatScore(score) {
  if (typeof score !== 'number') return ''
  return `${Math.round(score * 100)}%`
}

function plural(n, one, few, many) {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}
</script>

<style scoped>
.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.compare-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.compare-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.compare-placeholder {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
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

.compare-meta {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
}

.closest-title {
  color: var(--text);
  font-weight: 500;
}

.section-title {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.paths-section {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.paths-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.path-item {
  min-width: 0;
}

.path-link {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--surface) 50%, transparent);
  cursor: pointer;
  text-align: left;
}

.path-link:hover {
  border-color: var(--accent);
}

.path-text {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  color: var(--text);
  word-break: break-all;
}

.path-text--plain {
  display: block;
  padding: 6px 8px;
  color: var(--text-muted);
}

.path-line {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.ai-section {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-output {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
  white-space: pre-wrap;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--surface) 50%, transparent);
}

.error-msg {
  font-size: 12px;
  color: var(--danger);
  margin: 0;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 11px;
}
</style>
