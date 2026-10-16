<template>
  <div class="anon-monaco">
    <div ref="container" class="anon-monaco-container" />
    <p v-if="showPlaceholder" class="anon-monaco-placeholder">{{ placeholder }}</p>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import loader from '@monaco-editor/loader'
import { useTheme } from '../../composables/useTheme'

const props = defineProps({
  /** 'edit' | 'view' | 'diff' */
  mode: { type: String, default: 'view' },
  modelValue: { type: String, default: '' },
  /** Left side of the diff. */
  original: { type: String, default: '' },
  placeholder: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const { isDark } = useTheme()
const container = ref(null)
let monaco = null
let editor = null
let diffEditor = null
let originalModel = null
let modifiedModel = null
let suppress = false
let disposed = false

const showPlaceholder = computed(() => props.mode !== 'diff' && !props.modelValue && props.placeholder)

const baseOptions = () => ({
  language: 'xml',
  theme: isDark.value ? 'vs-dark' : 'vs',
  minimap: { enabled: false },
  wordWrap: 'on',
  fontSize: 13,
  fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
  tabSize: 2,
  scrollBeyondLastLine: false,
  automaticLayout: true,
})

function teardown() {
  editor?.dispose()
  editor = null
  diffEditor?.dispose()
  diffEditor = null
  originalModel?.dispose()
  originalModel = null
  modifiedModel?.dispose()
  modifiedModel = null
}

function build() {
  if (!monaco || !container.value || disposed) return
  teardown()
  if (props.mode === 'diff') {
    diffEditor = monaco.editor.createDiffEditor(container.value, {
      ...baseOptions(),
      readOnly: true,
      renderSideBySide: true,
      originalEditable: false,
    })
    originalModel = monaco.editor.createModel(props.original || '', 'xml')
    modifiedModel = monaco.editor.createModel(props.modelValue || '', 'xml')
    diffEditor.setModel({ original: originalModel, modified: modifiedModel })
    return
  }
  editor = monaco.editor.create(container.value, {
    ...baseOptions(),
    value: props.modelValue || '',
    readOnly: props.mode !== 'edit',
    domReadOnly: props.mode !== 'edit',
  })
  editor.onDidChangeModelContent(() => {
    if (suppress || props.mode !== 'edit') return
    emit('update:modelValue', editor.getValue())
  })
}

onMounted(async () => {
  monaco = await loader.init()
  build()
})

onBeforeUnmount(() => {
  disposed = true
  teardown()
})

watch(() => props.mode, build)

watch(
  () => props.modelValue,
  (value) => {
    const next = value || ''
    if (editor) {
      if (editor.getValue() === next) return
      suppress = true
      try {
        editor.setValue(next)
      } finally {
        suppress = false
      }
    } else if (modifiedModel && modifiedModel.getValue() !== next) {
      modifiedModel.setValue(next)
    }
  },
)

watch(
  () => props.original,
  (value) => {
    if (originalModel && originalModel.getValue() !== (value || '')) {
      originalModel.setValue(value || '')
    }
  },
)

watch(isDark, (dark) => {
  monaco?.editor.setTheme(dark ? 'vs-dark' : 'vs')
})

function goToLine(line) {
  const target = editor || diffEditor?.getModifiedEditor()
  if (!target || !line || line < 1) return
  target.revealLineInCenter(line)
  target.setPosition({ lineNumber: line, column: 1 })
  target.focus()
}

defineExpose({ goToLine })
</script>

<style scoped>
.anon-monaco {
  position: relative;
  flex: 1;
  min-height: 0;
  height: 100%;
}

.anon-monaco-container {
  height: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.anon-monaco-placeholder {
  position: absolute;
  top: 12px;
  left: 56px;
  right: 16px;
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-muted);
  pointer-events: none;
  white-space: pre-line;
}
</style>
