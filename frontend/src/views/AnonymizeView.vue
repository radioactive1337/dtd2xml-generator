<template>
  <div class="anon-page">
    <div class="anon-left" :style="{ width: leftWidth + 'px' }">
      <div class="card anon-card">
        <div class="steps" role="tablist" aria-label="Шаги анонимизации">
          <button
            v-for="tab in tabs"
            :id="`anon-tab-${tab.id}`"
            :key="tab.id"
            type="button"
            role="tab"
            class="step"
            :class="{ active: activeTab === tab.id }"
            :aria-selected="activeTab === tab.id"
            @click="activeTab = tab.id"
          >
            <span v-if="tab.num" class="step-num">{{ tab.num }}</span>
            {{ tab.label }}
            <span v-if="tab.badge" class="step-badge" :class="tab.badgeTone">{{ tab.badge }}</span>
          </button>
        </div>

        <div class="tab-body" role="tabpanel" :aria-labelledby="`anon-tab-${activeTab}`">
          <AnonymizeSettings v-show="activeTab === 'prepare'" :ctx="ctx" />

          <div v-show="activeTab === 'check'" class="check-tab">
            <div class="subtabs">
              <button
                type="button"
                class="subtab"
                :class="{ active: checkTab === 'findings' }"
                @click="checkTab = 'findings'"
              >
                Находки
                <span v-if="ctx.analysis" class="step-badge">{{ ctx.analysis.stats.replace }}</span>
              </button>
              <button
                type="button"
                class="subtab"
                :class="{ active: checkTab === 'queue' }"
                @click="checkTab = 'queue'"
              >
                Не классифицировано
                <span
                  v-if="ctx.analysis"
                  class="step-badge"
                  :class="{ warn: ctx.analysis.stats.unclassified_suspicious > 0 }"
                >
                  {{ ctx.analysis.stats.unclassified }}
                </span>
              </button>
            </div>
            <p v-if="ctx.analyzeError" class="error-msg">{{ ctx.analyzeError }}</p>
            <AnonymizeFindings v-show="checkTab === 'findings'" :ctx="ctx" @go-to-line="goToSourceLine" />
            <AnonymizeQueue v-show="checkTab === 'queue'" :ctx="ctx" @go-to-line="goToSourceLine" />
          </div>

          <AnonymizeReport
            v-show="activeTab === 'result'"
            :ctx="ctx"
            @go-to-line="goToResultLine"
            @open-queue="openQueue"
          />

          <AnonymizeRulesPanel v-show="activeTab === 'rules'" :ctx="ctx" />
        </div>

        <div class="footer">
          <p v-if="ctx.analyzing" class="footer-hint">Анализ…</p>
          <p v-else-if="ctx.analysis && ctx.analysis.stats.unclassified_suspicious" class="footer-hint warn">
            Подозрительных неклассифицированных полей: {{ ctx.analysis.stats.unclassified_suspicious }}
          </p>
          <button
            type="button"
            class="btn-primary run"
            :disabled="!ctx.hasSource || ctx.applying || ctx.analyzing"
            @click="run"
          >
            {{ ctx.applying ? 'Анонимизация…' : 'Анонимизировать' }}
          </button>
        </div>
      </div>
    </div>

    <div class="col-divider" title="Потяните для изменения ширины" @mousedown.prevent="startResize" />

    <div class="anon-right">
      <div class="right-head">
        <div class="view-tabs">
          <button type="button" class="view-tab" :class="{ active: view === 'source' }" @click="view = 'source'">
            Исходный XML
          </button>
          <button
            type="button"
            class="view-tab"
            :class="{ active: view === 'result' }"
            :disabled="!ctx.result"
            @click="view = 'result'"
          >
            Результат
          </button>
        </div>
        <template v-if="view === 'result' && ctx.result">
          <button
            type="button"
            class="btn-secondary btn-sm"
            :title="ctx.showOriginal ? 'Скрыть оригинал' : 'Показать оригинал рядом с результатом (на экране будут реальные данные)'"
            @click="ctx.showOriginal = !ctx.showOriginal"
          >
            {{ ctx.showOriginal ? 'Скрыть оригинал' : 'Сравнить с оригиналом' }}
          </button>
        </template>
        <span v-if="ctx.result" class="badge" :class="`tone-${ctx.status.tone}`">{{ ctx.status.label }}</span>
        <span v-if="ctx.resultStale" class="badge tone-muted">устарел</span>
      </div>

      <div class="editor-wrap">
        <AnonymizeMonaco
          v-if="view === 'source'"
          ref="sourceEditor"
          mode="edit"
          :model-value="ctx.sourceXml"
          placeholder="Вставьте XML реального человека (Ctrl+V) или нажмите «Импорт .xml» слева.&#10;Данные остаются в памяти этой страницы и не сохраняются."
          @update:model-value="ctx.onSourceEdited"
        />
        <AnonymizeMonaco
          v-else
          ref="resultEditor"
          :mode="ctx.showOriginal ? 'diff' : 'view'"
          :model-value="ctx.resultXml"
          :original="ctx.sourceXml"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'AnonymizeView' })

import { computed, nextTick, ref, watch } from 'vue'
import AnonymizeMonaco from '../components/anonymize/AnonymizeMonaco.vue'
import AnonymizeSettings from '../components/anonymize/AnonymizeSettings.vue'
import AnonymizeFindings from '../components/anonymize/AnonymizeFindings.vue'
import AnonymizeQueue from '../components/anonymize/AnonymizeQueue.vue'
import AnonymizeReport from '../components/anonymize/AnonymizeReport.vue'
import AnonymizeRulesPanel from '../components/anonymize/AnonymizeRulesPanel.vue'
import { useAnonymize } from '../composables/useAnonymize'

const ctx = useAnonymize()

const activeTab = ref('prepare')
const checkTab = ref('queue')
const view = ref('source')
const sourceEditor = ref(null)
const resultEditor = ref(null)

const leftWidth = ref(500)

const tabs = computed(() => {
  const stats = ctx.analysis?.stats
  return [
    { id: 'prepare', num: 1, label: 'Подготовка' },
    {
      id: 'check',
      num: 2,
      label: 'Проверка',
      badge: stats?.unclassified_suspicious || '',
      badgeTone: 'warn',
    },
    {
      id: 'result',
      num: 3,
      label: 'Результат',
      badge: ctx.report ? ctx.report.replaced : '',
      badgeTone: ctx.status.tone === 'warning' ? 'warn' : '',
    },
    { id: 'rules', num: 0, label: 'Правила', badge: ctx.rules.userRules.length || '' },
  ]
})

// Once a document is loaded, jump to the review step.
watch(
  () => ctx.analysis,
  (value, prev) => {
    if (value && !prev && activeTab.value === 'prepare') {
      checkTab.value = value.stats.unclassified ? 'queue' : 'findings'
      activeTab.value = 'check'
    }
  },
)

watch(
  () => ctx.hasSource,
  (has) => {
    if (!has) {
      view.value = 'source'
      activeTab.value = 'prepare'
    }
  },
)

async function run() {
  const ok = await ctx.apply()
  if (ok) {
    view.value = 'result'
    activeTab.value = 'result'
  }
}

function openQueue() {
  checkTab.value = 'queue'
  activeTab.value = 'check'
}

async function goToSourceLine(line) {
  view.value = 'source'
  await nextTick()
  sourceEditor.value?.goToLine(line)
}

async function goToResultLine(line) {
  view.value = 'result'
  await nextTick()
  resultEditor.value?.goToLine(line)
}

function startResize(event) {
  const startX = event.clientX
  const startWidth = leftWidth.value
  const onMove = (e) => {
    leftWidth.value = Math.min(800, Math.max(420, startWidth + e.clientX - startX))
  }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
</script>

<style scoped>
.anon-page {
  display: flex;
  align-items: stretch;
  height: 100%;
  flex: 1;
  min-height: 0;
}

.anon-left {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  min-width: 420px;
  height: 100%;
}

.anon-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

.steps {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.step {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 6px;
  font-size: 13px;
  color: var(--text-muted);
  background: transparent;
  border-radius: 0;
  border-bottom: 2px solid transparent;
}

.step:hover {
  color: var(--text);
}

.step.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.step-num {
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  border-radius: 50%;
  background: var(--surface2);
  border: 1px solid var(--border);
}

.step-badge {
  padding: 0 6px;
  font-size: 11px;
  line-height: 16px;
  border-radius: 8px;
  background: var(--border);
  color: var(--text-muted);
}

.step-badge.warn {
  background: color-mix(in srgb, var(--warning) 22%, transparent);
  color: var(--warning);
}

.tab-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}

.check-tab {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.subtabs {
  display: flex;
  gap: 4px;
}

.subtab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--surface2);
  border: 1px solid var(--border);
}

.subtab.active {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 50%, var(--border));
}

.footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.footer-hint {
  flex: 1;
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.footer-hint.warn {
  color: var(--warning);
}

.run {
  margin-left: auto;
}

.col-divider {
  width: 8px;
  align-self: stretch;
  cursor: col-resize;
  position: relative;
  flex-shrink: 0;
}

.col-divider::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  transform: translateX(-50%);
  background: var(--border);
  border-radius: 2px;
  transition: background 0.15s;
}

.col-divider:hover::after {
  background: var(--accent);
}

.anon-right {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.right-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.view-tabs {
  display: flex;
  gap: 4px;
  margin-right: auto;
}

.view-tab {
  padding: 5px 12px;
  font-size: 13px;
  color: var(--text-muted);
  background: var(--surface2);
  border: 1px solid var(--border);
}

.view-tab.active {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 50%, var(--border));
}

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}

.badge {
  padding: 2px 9px;
  font-size: 11px;
  border-radius: 10px;
  border: 1px solid var(--border);
  color: var(--text-muted);
}

.badge.tone-success {
  color: var(--success);
  border-color: color-mix(in srgb, var(--success) 45%, var(--border));
}

.badge.tone-warning {
  color: var(--warning);
  border-color: color-mix(in srgb, var(--warning) 45%, var(--border));
}

.editor-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

@media (max-width: 900px) {
  .anon-page {
    flex-direction: column;
    overflow-y: auto;
  }
  .anon-left {
    width: 100% !important;
    min-width: 0;
    height: auto;
  }
  .col-divider {
    display: none;
  }
  .anon-right {
    min-height: 420px;
  }
}
</style>
