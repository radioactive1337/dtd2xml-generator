<template>
  <div class="xml-editor card">
    <div class="editor-header">
      <div class="panel-title">XML Preview</div>
      <div class="editor-actions">
        <button class="btn-secondary" :disabled="!modelValue" @click="copyToClipboard">
          {{ copied ? 'Copied!' : 'Copy' }}
        </button>
        <button class="btn-secondary" :disabled="!modelValue" @click="downloadXml">
          Download .xml
        </button>
      </div>
    </div>
    <div ref="editorContainer" class="editor-container" :style="{ height: editorHeight + 'px' }" />
    <div class="resize-handle" @mousedown.prevent="startResize" title="Drag to resize" />
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import loader from '@monaco-editor/loader'

const props = defineProps({
  modelValue: { type: String, default: '' },
  filename: { type: String, default: 'generated.xml' },
})

const editorContainer = ref(null)
const copied = ref(false)
const editorHeight = ref(700)
let editor = null
let monaco = null

onMounted(async () => {
  monaco = await loader.init()
  editor = monaco.editor.create(editorContainer.value, {
    value: props.modelValue,
    language: 'xml',
    theme: 'vs-dark',
    readOnly: false,
    minimap: { enabled: false },
    wordWrap: 'on',
    fontSize: 13,
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

onBeforeUnmount(() => {
  editor?.dispose()
  stopResize()
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

// ---- Resize logic ----
let resizing = false
let resizeStartY = 0
let resizeStartHeight = 0

function startResize(e) {
  resizing = true
  resizeStartY = e.clientY
  resizeStartHeight = editorHeight.value
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
}

function onResizeMove(e) {
  if (!resizing) return
  const delta = e.clientY - resizeStartY
  editorHeight.value = Math.max(150, resizeStartHeight + delta)
}

function stopResize() {
  resizing = false
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
</script>

<style scoped>
.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.editor-actions {
  display: flex;
  gap: 8px;
}

.editor-container {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: height 0s;
}

.resize-handle {
  height: 10px;
  cursor: row-resize;
  position: relative;
  margin-top: 4px;
}

.resize-handle::after {
  content: '';
  position: absolute;
  left: 30%;
  right: 30%;
  top: 50%;
  height: 3px;
  transform: translateY(-50%);
  background: var(--border);
  border-radius: 2px;
  transition: background 0.15s;
}

.resize-handle:hover::after {
  background: var(--accent);
}
</style>
