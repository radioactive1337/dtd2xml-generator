<template>
  <div class="xml-editor card">
    <div class="editor-header">
      <div class="panel-title">XML Preview</div>
      <div class="editor-actions">
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

const editorContainer = ref(null)
const copied = ref(false)
let editor = null
let monaco = null

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

  editor.onDidChangeModelContent(() => {
    emit('update:modelValue', editor.getValue())
  })
})

const emit = defineEmits(['update:modelValue'])

watch(
  () => props.modelValue,
  (val) => {
    if (editor && editor.getValue() !== val) {
      editor.setValue(val || '')
    }
  },
)

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

defineExpose({ goToPosition })
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

.editor-container {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
</style>
