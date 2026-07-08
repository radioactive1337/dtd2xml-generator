<template>
  <div class="xml-editor card">
    <div class="editor-header">
      <div class="editor-actions">
        <input
          ref="fileInput"
          type="file"
          accept=".xml,text/xml,application/xml"
          style="display: none"
          @change="onFileSelect"
        />

        <div class="action-group">
          <button
            class="btn-secondary btn-tint btn-tint-import"
            title="Загрузить XML из файла"
            @click="triggerImport"
          >
            Импорт .xml
          </button>
        </div>

        <div class="action-group">
          <button
            class="btn-secondary btn-tint btn-tint-format"
            :disabled="!modelValue"
            title="Форматировать документ (Alt+Shift+F)"
            @click="formatDocument"
          >
            <span class="format-icon" aria-hidden="true">{ }</span>Форматировать
          </button>
          <button
            class="btn-secondary btn-tint btn-tint-danger"
            :disabled="!modelValue"
            title="Очистить содержимое редактора"
            @click="clearEditor"
          >
            Очистить
          </button>
        </div>

        <div v-if="showCompareButton" class="action-group">
          <button
            class="btn-secondary btn-tint btn-tint-compare"
            :disabled="!modelValue || comparing"
            title="Сравнить структуру XML со всеми эталонами того же корневого элемента"
            @click="$emit('run-compare')"
          >
            {{ comparing ? 'Проверяем…' : 'Проверить уникальность' }}
          </button>
        </div>

        <div class="action-group">
          <button
            class="btn-secondary btn-tint btn-tint-export"
            :disabled="!modelValue"
            @click="downloadXml"
          >
            Экспорт .xml
          </button>
          <button
            v-if="gitPushEnabled"
            class="btn-secondary btn-tint btn-tint-git"
            :disabled="!modelValue"
            title="Отправить в Git-репозиторий эталонной библиотеки"
            @click="onGitPushClick"
          >
            Отправить в Git
          </button>
          <button
            class="btn-secondary btn-tint btn-tint-share"
            :disabled="!modelValue"
            title="Поделиться с другим пользователем"
            @click="onShareClick"
          >
            Поделиться
          </button>
          <button
            class="btn-secondary btn-tint btn-tint-save"
            :disabled="!canSave"
            title="Сохранить в «Мои документы»"
            @click="onSaveClick"
          >
            Сохранить в документы
          </button>
        </div>
      </div>
    </div>
    <p v-if="importError" class="import-error">{{ importError }}</p>
    <div ref="editorContainer" class="editor-container" />

    <div v-if="showPushDialog" class="save-dialog-backdrop" @click.self="closePushDialog">
      <form class="save-dialog" @submit.prevent="submitPush">
        <h4 class="save-dialog-title">Отправить в Git</h4>
        <p v-if="rootElement" class="push-path-hint">
          Путь: <code>{{ pushTargetPath }}</code>
        </p>
        <p class="push-overwrite-hint">
          Если файл уже есть в репозитории, он будет перезаписан.
        </p>
        <label class="save-label">
          Имя файла
          <input
            v-model="pushFilename"
            type="text"
            class="save-input"
            required
            :disabled="gitPushSubmitting"
            autofocus
          />
        </label>
        <label class="save-label">
          Сообщение коммита (необязательно)
          <input
            v-model="pushCommitMessage"
            type="text"
            class="save-input"
            :disabled="gitPushSubmitting"
          />
        </label>
        <p v-if="gitPushError" class="push-feedback push-feedback-error">{{ gitPushError }}</p>
        <p v-else-if="gitPushMessage" class="push-feedback push-feedback-success">{{ gitPushMessage }}</p>
        <div class="save-dialog-actions">
          <button
            type="button"
            class="btn-secondary btn-sm"
            :disabled="gitPushSubmitting"
            @click="closePushDialog"
          >
            {{ gitPushMessage ? 'Закрыть' : 'Отмена' }}
          </button>
          <button
            v-if="!gitPushMessage"
            type="submit"
            class="btn-primary btn-sm"
            :disabled="!pushFilename.trim() || gitPushSubmitting"
          >
            {{ gitPushSubmitting ? 'Отправка…' : 'Отправить' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="showSaveDialog" class="save-dialog-backdrop" @click.self="closeSaveDialog">
      <form class="save-dialog" @submit.prevent="submitSave">
        <h4 class="save-dialog-title">Сохранить XML</h4>
        <label class="save-label">
          Имя
          <input v-model="saveName" type="text" class="save-input" required autofocus />
        </label>
        <label class="save-label">
          Описание (необязательно)
          <input v-model="saveDescription" type="text" class="save-input" />
        </label>
        <div class="save-dialog-actions">
          <button type="button" class="btn-secondary btn-sm" @click="closeSaveDialog">Отмена</button>
          <button type="submit" class="btn-primary btn-sm" :disabled="!saveName.trim()">Сохранить</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import loader from '@monaco-editor/loader'
import { registerXmlFormatter } from '../utils/formatXml'
import { readXmlFileAsText } from '../utils/readXmlFile'
import { useTheme } from '../composables/useTheme'

const props = defineProps({
  modelValue: { type: String, default: '' },
  filename: { type: String, default: 'generated.xml' },
  validationErrors: { type: Array, default: () => [] },
  canSave: { type: Boolean, default: false },
  uniqueRanges: { type: Array, default: () => [] },
  gitPushEnabled: { type: Boolean, default: false },
  rootElement: { type: String, default: '' },
  gitPushSubmitting: { type: Boolean, default: false },
  gitPushMessage: { type: String, default: '' },
  gitPushError: { type: String, default: '' },
  showCompareButton: { type: Boolean, default: false },
  comparing: { type: Boolean, default: false },
})

const emit = defineEmits([
  'content-change',
  'import',
  'clear',
  'save',
  'share',
  'push-to-git',
  'push-dialog-open',
  'push-dialog-close',
  'run-compare',
])

const { isDark } = useTheme()

const editorContainer = ref(null)
const fileInput = ref(null)
const importError = ref('')
const showSaveDialog = ref(false)
const showPushDialog = ref(false)
const saveName = ref('')
const saveDescription = ref('')
const pushFilename = ref('')
const pushCommitMessage = ref('')

const pushTargetPath = computed(() => {
  const folder = props.rootElement || 'root'
  const file = pushFilename.value.trim() || 'document.xml'
  return `${folder}/${file}`
})

function defaultPushFilename() {
  const base = (props.filename || 'generated.xml').replace(/\.xml$/i, '')
  return `${base || 'document'}.xml`
}
let editor = null
let monaco = null
let suppressEditorEvent = false
let pasteFlushTimer = null
let uniqueDecorations = null

function applyModelValue(val) {
  if (!editor) return
  const next = val || ''
  if (editor.getValue() === next) return
  suppressEditorEvent = true
  editor.setValue(next)
  suppressEditorEvent = false
  editor.layout()
}

function onModelContentChanged() {
  clearUniqueDecorations()
  notifyContentChange()
}

function notifyContentChange() {
  if (suppressEditorEvent || !editor) return
  emit('content-change', editor.getValue())
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function tagRangeOnLine(model, line, tag) {
  const text = model.getLineContent(line)
  const match = new RegExp(`<${escapeRegExp(tag)}(?=[\\s/>])`).exec(text)
  if (!match) return null
  const startColumn = match.index + 1
  const endColumn = startColumn + 1 + tag.length
  return { startColumn, endColumn }
}

function applyUniqueDecorations(targets) {
  if (!editor || !monaco) return
  const model = editor.getModel()
  if (!model) return
  const lineCount = model.getLineCount()
  const list = []

  for (const t of targets || []) {
    // Support both the element-target shape ({ line, tag }) and legacy line ranges.
    const line = t?.line ?? t?.start_line
    if (!line || line < 1 || line > lineCount) continue
    const hover = {
      value: `Уникальный элемент: ${t.path || t.tag || ''} (нет ни в одном эталоне)`,
    }

    let range = null
    if (t.tag) {
      const cols = tagRangeOnLine(model, line, t.tag)
      if (cols) range = new monaco.Range(line, cols.startColumn, line, cols.endColumn)
    }

    if (range) {
      list.push({
        range,
        options: {
          className: 'xml-unique-token',
          glyphMarginClassName: 'xml-unique-glyph',
          glyphMarginHoverMessage: hover,
          hoverMessage: hover,
          overviewRuler: {
            color: '#f59e0b',
            position: monaco.editor.OverviewRulerLane.Right,
          },
        },
      })
    } else {
      // Fallback: no tag found on the line — mark the whole line.
      list.push({
        range: new monaco.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          className: 'xml-unique-line',
          glyphMarginClassName: 'xml-unique-glyph',
          glyphMarginHoverMessage: hover,
          overviewRuler: {
            color: '#f59e0b',
            position: monaco.editor.OverviewRulerLane.Right,
          },
        },
      })
    }
  }

  if (uniqueDecorations) {
    uniqueDecorations.set(list)
  } else {
    uniqueDecorations = editor.createDecorationsCollection(list)
  }
}

function clearUniqueDecorations() {
  if (uniqueDecorations) {
    uniqueDecorations.clear()
    uniqueDecorations = null
  }
}

function setValue(val) {
  applyModelValue(val || '')
}

function schedulePasteFlush() {
  clearTimeout(pasteFlushTimer)
  pasteFlushTimer = setTimeout(notifyContentChange, 0)
}

onMounted(async () => {
  monaco = await loader.init()
  registerXmlFormatter(monaco)
  editor = monaco.editor.create(editorContainer.value, {
    value: props.modelValue,
    language: 'xml',
    theme: isDark.value ? 'vs-dark' : 'vs',
    readOnly: false,
    minimap: { enabled: false },
    wordWrap: 'on',
    fontSize: 13,
    tabSize: 2,
    glyphMargin: true,
    scrollBeyondLastLine: false,
    automaticLayout: true,
  })

  editor.onDidChangeModelContent(onModelContentChanged)
  editor.onDidPaste(schedulePasteFlush)
  applyModelValue(props.modelValue)
  if (props.uniqueRanges?.length) applyUniqueDecorations(props.uniqueRanges)
})

watch(() => props.modelValue, applyModelValue)

watch(
  () => props.uniqueRanges,
  (ranges) => applyUniqueDecorations(ranges),
  { deep: true },
)

watch(isDark, (dark) => {
  if (monaco) monaco.editor.setTheme(dark ? 'vs-dark' : 'vs')
})

watch(
  () => props.validationErrors,
  (errors) => {
    if (!editor || !monaco) return
    const model = editor.getModel()
    if (!model) return

    const markers = errors
      .filter((err) => err.line > 0)
      .map((err) => ({
        severity: monaco.MarkerSeverity.Error,
        startLineNumber: err.line,
        startColumn: err.column || 1,
        endLineNumber: err.line,
        endColumn: (err.column || 1) + 1,
        message: err.message,
      }))

    monaco.editor.setModelMarkers(model, 'dtd-validation', markers)
  },
  { deep: true },
)

onBeforeUnmount(() => {
  clearTimeout(pasteFlushTimer)
  editor?.dispose()
})

function downloadXml() {
  if (!props.modelValue) return
  const blob = new Blob([props.modelValue], { type: 'application/xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = props.filename
  a.click()
  URL.revokeObjectURL(url)
}

function triggerImport() {
  importError.value = ''
  fileInput.value?.click()
}

async function onFileSelect(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return

  importError.value = ''
  try {
    const text = await readXmlFileAsText(file)
    if (!text.trim()) {
      importError.value = 'Файл пуст'
      return
    }
    emit('import', { text, fileName: file.name })
  } catch (err) {
    importError.value = err.message || 'Не удалось импортировать XML'
  }
}

async function formatDocument() {
  if (!editor) return
  await editor.getAction('editor.action.formatDocument')?.run()
}

function clearEditor() {
  if (!props.modelValue) return
  emit('clear')
}

function onGitPushClick() {
  pushFilename.value = defaultPushFilename()
  pushCommitMessage.value = ''
  showPushDialog.value = true
  emit('push-dialog-open')
}

function closePushDialog() {
  if (props.gitPushSubmitting) return
  showPushDialog.value = false
  emit('push-dialog-close')
}

function submitPush() {
  const filename = pushFilename.value.trim()
  if (!filename || props.gitPushSubmitting) return
  emit('push-to-git', {
    filename,
    commitMessage: pushCommitMessage.value.trim(),
  })
}

watch(
  () => props.gitPushMessage,
  (message) => {
    if (message) showPushDialog.value = true
  },
)

function onSaveClick() {
  saveName.value = ''
  saveDescription.value = ''
  showSaveDialog.value = true
}

function onShareClick() {
  emit('share')
}

function closeSaveDialog() {
  showSaveDialog.value = false
}

function submitSave() {
  const name = saveName.value.trim()
  if (!name) return
  emit('save', { name, description: saveDescription.value.trim() })
  closeSaveDialog()
}

function goToPosition(line, column) {
  if (!editor || !line || line < 1) return
  const position = { lineNumber: line, column: column > 0 ? column : 1 }
  editor.setPosition(position)
  editor.revealPositionInCenter(position)
  editor.focus()
}

function getValue() {
  return editor?.getValue() ?? props.modelValue ?? ''
}

defineExpose({ goToPosition, getValue, setValue, clearUniqueDecorations })
</script>

<style scoped>
.xml-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
}

.action-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-group + .action-group {
  margin-left: 8px;
  padding-left: 8px;
  border-left: 1px solid var(--border);
}

.editor-actions .btn-tint {
  transition: background 0.15s, border-color 0.15s;
}

.editor-actions .btn-tint-import {
  background: color-mix(in srgb, var(--accent) 14%, var(--surface2));
  border-color: color-mix(in srgb, var(--accent) 38%, var(--border));
}
.editor-actions .btn-tint-import:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 22%, var(--surface2));
  border-color: color-mix(in srgb, var(--accent) 48%, var(--border));
}

.editor-actions .btn-tint-format {
  background: color-mix(in srgb, var(--llm-accent) 14%, var(--surface2));
  border-color: color-mix(in srgb, var(--llm-accent) 36%, var(--border));
}
.editor-actions .btn-tint-format:hover:not(:disabled) {
  background: color-mix(in srgb, var(--llm-accent) 22%, var(--surface2));
  border-color: color-mix(in srgb, var(--llm-accent) 46%, var(--border));
}

.editor-actions .btn-tint-danger {
  background: color-mix(in srgb, var(--danger) 12%, var(--surface2));
  border-color: color-mix(in srgb, var(--danger) 34%, var(--border));
}
.editor-actions .btn-tint-danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--danger) 20%, var(--surface2));
  border-color: color-mix(in srgb, var(--danger) 44%, var(--border));
}

.editor-actions .btn-tint-export {
  background: color-mix(in srgb, var(--success) 13%, var(--surface2));
  border-color: color-mix(in srgb, var(--success) 36%, var(--border));
}
.editor-actions .btn-tint-export:hover:not(:disabled) {
  background: color-mix(in srgb, var(--success) 21%, var(--surface2));
  border-color: color-mix(in srgb, var(--success) 46%, var(--border));
}

.editor-actions .btn-tint-git {
  background: color-mix(in srgb, var(--warning) 14%, var(--surface2));
  border-color: color-mix(in srgb, var(--warning) 38%, var(--border));
}
.editor-actions .btn-tint-git:hover:not(:disabled) {
  background: color-mix(in srgb, var(--warning) 22%, var(--surface2));
  border-color: color-mix(in srgb, var(--warning) 48%, var(--border));
}

.editor-actions .btn-tint-share {
  background: color-mix(in srgb, #06b6d4 13%, var(--surface2));
  border-color: color-mix(in srgb, #06b6d4 35%, var(--border));
}
.editor-actions .btn-tint-share:hover:not(:disabled) {
  background: color-mix(in srgb, #06b6d4 21%, var(--surface2));
  border-color: color-mix(in srgb, #06b6d4 45%, var(--border));
}

.editor-actions .btn-tint-save {
  background: color-mix(in srgb, var(--accent) 18%, var(--surface2));
  border-color: color-mix(in srgb, var(--accent) 44%, var(--border));
}
.editor-actions .btn-tint-save:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 26%, var(--surface2));
  border-color: color-mix(in srgb, var(--accent) 54%, var(--border));
}

.editor-actions .btn-tint-compare {
  background: color-mix(in srgb, var(--warning) 14%, var(--surface2));
  border-color: color-mix(in srgb, var(--warning) 38%, var(--border));
}
.editor-actions .btn-tint-compare:hover:not(:disabled) {
  background: color-mix(in srgb, var(--warning) 22%, var(--surface2));
  border-color: color-mix(in srgb, var(--warning) 48%, var(--border));
}

.format-icon {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-weight: 600;
  margin-right: 4px;
}

.import-error {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--danger, #ef4444);
}

.editor-container {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 11px;
}

.save-dialog-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--bg, #000) 40%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.save-dialog {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  width: min(360px, 90vw);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.save-dialog-title {
  margin: 0;
  font-size: 14px;
}

.save-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.save-input {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
}

.save-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

.push-path-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.push-path-hint code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
}

.push-overwrite-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.push-feedback {
  margin: 0;
  font-size: 12px;
}

.push-feedback-error {
  color: var(--danger, #ef4444);
}

.push-feedback-success {
  color: var(--success, #22c55e);
}
</style>

<style>
/* Not scoped: Monaco renders decoration nodes outside the component scope. */
.xml-unique-token {
  background: rgba(245, 158, 11, 0.28);
  border-radius: 3px;
  box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.55);
}

.xml-unique-line {
  background: rgba(245, 158, 11, 0.16);
}

.xml-unique-glyph {
  background: #f59e0b;
  width: 4px !important;
  margin-left: 3px;
  border-radius: 2px;
}
</style>
