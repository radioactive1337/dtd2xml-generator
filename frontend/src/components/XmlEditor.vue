<template>
  <div class="xml-editor card">
    <div class="editor-header">
      <div class="panel-title">XML Preview</div>
      <div class="editor-actions">
        <input
          ref="fileInput"
          type="file"
          accept=".xml,text/xml,application/xml"
          style="display: none"
          @change="onFileSelect"
        />
        <button
          class="btn-secondary"
          title="Load XML from a file"
          @click="triggerImport"
        >
          Import .xml
        </button>
        <button
          class="btn-secondary btn-format"
          :disabled="!modelValue"
          title="Format document (Alt+Shift+F)"
          @click="formatDocument"
        >
          <span class="format-icon" aria-hidden="true">{ }</span>Format
        </button>
        <button class="btn-secondary" :disabled="!modelValue" @click="copyToClipboard">
          {{ copied ? 'Copied!' : 'Copy' }}
        </button>
        <button class="btn-secondary" :disabled="!modelValue" @click="downloadXml">
          Download .xml
        </button>
      </div>
    </div>
    <p v-if="importError" class="import-error">{{ importError }}</p>
    <div ref="editorContainer" class="editor-container" />
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import loader from '@monaco-editor/loader'
import { registerXmlFormatter } from '../utils/formatXml'

const props = defineProps({
  modelValue: { type: String, default: '' },
  filename: { type: String, default: 'generated.xml' },
  validationErrors: { type: Array, default: () => [] },
})

const emit = defineEmits(['content-change', 'import'])

const editorContainer = ref(null)
const fileInput = ref(null)
const copied = ref(false)
const importError = ref('')
let editor = null
let monaco = null
let suppressEditorEvent = false
let pasteFlushTimer = null

function applyModelValue(val) {
  if (!editor) return
  const next = val || ''
  if (editor.getValue() === next) return
  suppressEditorEvent = true
  editor.setValue(next)
  suppressEditorEvent = false
  editor.layout()
}

function notifyContentChange() {
  if (suppressEditorEvent || !editor) return
  emit('content-change', editor.getValue())
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
    theme: 'vs-dark',
    readOnly: false,
    minimap: { enabled: false },
    wordWrap: 'on',
    fontSize: 13,
    tabSize: 2,
    scrollBeyondLastLine: false,
    automaticLayout: true,
  })

  editor.onDidChangeModelContent(notifyContentChange)
  editor.onDidPaste(schedulePasteFlush)
  applyModelValue(props.modelValue)
})

watch(() => props.modelValue, applyModelValue)

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

async function copyToClipboard() {
  if (!props.modelValue) return
  await navigator.clipboard.writeText(props.modelValue)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

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

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(new Error('Failed to read file'))
    reader.readAsText(file, 'UTF-8')
  })
}

async function onFileSelect(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return

  importError.value = ''
  try {
    const text = await readFileAsText(file)
    if (!text.trim()) {
      importError.value = 'File is empty'
      return
    }
    emit('import', { text, fileName: file.name })
  } catch (err) {
    importError.value = err.message || 'Failed to import XML file'
  }
}

async function formatDocument() {
  if (!editor) return
  await editor.getAction('editor.action.formatDocument')?.run()
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

defineExpose({ goToPosition, getValue, setValue })
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
  gap: 8px;
}

.btn-format {
  font-size: 12px;
  padding: 4px 10px;
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
</style>
