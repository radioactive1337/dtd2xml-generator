<template>
  <div class="xml-editor card">
    <div class="editor-header">
      <div class="panel-title">Просмотр XML</div>
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
            class="btn-secondary"
            title="Загрузить XML из файла"
            @click="triggerImport"
          >
            Импорт .xml
          </button>
        </div>

        <div class="action-group">
          <button
            class="btn-secondary"
            :disabled="!modelValue"
            title="Форматировать документ (Alt+Shift+F)"
            @click="formatDocument"
          >
            <span class="format-icon" aria-hidden="true">{ }</span>Форматировать
          </button>
          <button
            class="btn-secondary"
            :disabled="!modelValue"
            title="Очистить содержимое редактора"
            @click="clearEditor"
          >
            Очистить
          </button>
        </div>

        <div class="action-group">
          <button class="btn-secondary" :disabled="!modelValue" @click="downloadXml">
            Экспорт .xml
          </button>
          <button
            class="btn-secondary"
            :disabled="!modelValue"
            title="Поделиться с другим пользователем"
            @click="onShareClick"
          >
            Поделиться
          </button>
          <button
            class="btn-secondary"
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
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
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
})

const emit = defineEmits(['content-change', 'import', 'clear', 'save', 'share'])

const { isDark } = useTheme()

const editorContainer = ref(null)
const fileInput = ref(null)
const importError = ref('')
const showSaveDialog = ref(false)
const saveName = ref('')
const saveDescription = ref('')
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

function applyUniqueDecorations(ranges) {
  if (!editor || !monaco) return
  const model = editor.getModel()
  if (!model) return
  const lineCount = model.getLineCount()
  const list = (ranges || [])
    .filter((r) => r && r.start_line > 0)
    .map((r) => {
      const start = Math.min(r.start_line, lineCount)
      const end = Math.min(r.end_line || r.start_line, lineCount)
      return {
        range: new monaco.Range(start, 1, Math.max(end, start), 1),
        options: {
          isWholeLine: true,
          className: 'xml-unique-line',
          glyphMarginClassName: 'xml-unique-glyph',
          glyphMarginHoverMessage: {
            value: `Уникальный путь: ${r.path} (нет ни в одном эталоне)`,
          },
          overviewRuler: {
            color: '#f59e0b',
            position: monaco.editor.OverviewRulerLane.Right,
          },
        },
      }
    })

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
</style>

<style>
/* Not scoped: Monaco renders decoration nodes outside the component scope. */
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
