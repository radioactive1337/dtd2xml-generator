<template>
  <div class="xml-editor">
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
            class="btn-secondary"
            :class="{ 'btn-tint btn-tint-import': !modelValue }"
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
            class="btn-secondary btn-tint btn-tint-danger"
            :disabled="!modelValue"
            title="Очистить содержимое редактора"
            @click="clearEditor"
          >
            Очистить
          </button>
          <button
            class="btn-secondary"
            :disabled="!hasSelection"
            title="Очистить значения всех атрибутов в выделении (attr=&quot;&quot;)"
            @click="clearAttributesInSelection"
          >
            Очистить значения атрибутов
          </button>
        </div>

        <div class="action-group">
          <button
            class="btn-secondary"
            :disabled="!modelValue"
            @click="downloadXml"
          >
            Экспорт .xml
          </button>
          <button
            class="btn-secondary"
            :disabled="!canSave"
            title="Сохранить в «Мои документы»"
            @click="onSaveClick"
          >
            Сохранить в документы
          </button>
          <div ref="moreRef" class="more-dropdown">
            <button
              type="button"
              class="btn-secondary more-dropdown-trigger"
              :class="{ open: moreOpen }"
              aria-haspopup="menu"
              :aria-expanded="moreOpen"
              @click="toggleMoreMenu"
            >
              Ещё
              <span class="more-dropdown-chevron" aria-hidden="true">▾</span>
            </button>
            <div v-if="moreOpen" class="more-dropdown-menu" role="menu" @click.stop>
              <button
                type="button"
                class="more-dropdown-item"
                role="menuitem"
                :disabled="!hasSelection"
                title="Экранировать спецсимволы в выделении (&, &lt;, &gt;, &quot;, &apos;)"
                @click="onMoreEscape"
              >
                Экранировать
              </button>
              <button
                type="button"
                class="more-dropdown-item"
                role="menuitem"
                :disabled="!hasSelection"
                title="Деэкранировать сущности в выделении (&amp;, &lt;, &gt;, &quot;, &apos;)"
                @click="onMoreUnescape"
              >
                Деэкранировать
              </button>
              <button
                v-if="showCompareButton"
                type="button"
                class="more-dropdown-item"
                role="menuitem"
                :disabled="!modelValue || comparing"
                title="Сравнить структуру XML со всеми эталонами того же корневого элемента"
                @click="onMoreCompare"
              >
                {{ comparing ? 'Проверяем…' : 'Проверить уникальность' }}
              </button>
              <button
                v-if="gitPushEnabled"
                type="button"
                class="more-dropdown-item"
                role="menuitem"
                :disabled="!modelValue"
                title="Отправить в Git-репозиторий эталонной библиотеки"
                @click="onMoreGitPush"
              >
                Отправить в Git
              </button>
              <button
                type="button"
                class="more-dropdown-item"
                role="menuitem"
                :disabled="!modelValue"
                title="Поделиться с другим пользователем"
                @click="onMoreShare"
              >
                Поделиться
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <p v-if="importError" class="import-error">{{ importError }}</p>
    <div class="editor-stage">
      <div ref="editorContainer" class="editor-container" />
    </div>

    <div v-if="showPushDialog" class="save-dialog-backdrop" @click.self="closePushDialog">
      <form class="save-dialog push-dialog" @submit.prevent="submitPush">
        <h4 class="save-dialog-title">Отправить в Git</h4>
        <p v-if="pushFolderName" class="push-path-hint">
          Путь: <code>{{ pushTargetPath }}</code>
        </p>
        <p class="push-overwrite-hint">
          Если файл уже есть в репозитории, он будет перезаписан.
        </p>
        <p class="push-fill-hint">
          Для отправки в Git должно быть заполнено не менее 15% атрибутов документа.
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
        <div v-if="gitPushWarnings.length" class="push-warnings">
          <p class="push-warnings-heading">{{ pushWarningsHeading }}</p>
          <ul class="push-warnings-list">
            <li v-for="(warning, index) in gitPushWarnings" :key="index">
              {{ formatPushWarningLabel(warning) }}
            </li>
          </ul>
          <p v-if="pushWarningsTruncated" class="push-warnings-more">
            … и ещё {{ gitPushWarningCount - gitPushWarnings.length }}
          </p>
          <label class="push-warnings-ack">
            <input
              v-model="warningsAcknowledged"
              type="checkbox"
              :disabled="gitPushSubmitting"
            />
            <span>Я ознакомился с предупреждениями и всё равно хочу отправить</span>
          </label>
        </div>
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
            :disabled="pushSubmitDisabled"
          >
            {{ pushSubmitLabel }}
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
import { onClickOutside } from '@vueuse/core'
import loader from '@monaco-editor/loader'
import { registerXmlFormatter } from '../utils/formatXml'
import { escapeXmlText, unescapeXmlText } from '../utils/escapeXml'
import { clearAttributeValues } from '../utils/clearAttributeValues'
import { readXmlFileAsText } from '../utils/readXmlFile'
import { peekXmlRootElement } from '../utils/xmlPaths'
import { formatPushWarningLabel } from '../utils/gitPushWarnings'
import { formatWarnings } from '../utils/ruPlural'
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
  gitPushWarnings: { type: Array, default: () => [] },
  gitPushWarningCount: { type: Number, default: 0 },
  showCompareButton: { type: Boolean, default: false },
  comparing: { type: Boolean, default: false },
})

const emit = defineEmits([
  'content-change',
  'import',
  'document-paste',
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
const hasSelection = ref(false)
const moreOpen = ref(false)
const moreRef = ref(null)

const pushFolderName = computed(
  () => peekXmlRootElement(props.modelValue) || props.rootElement || '',
)

const pushTargetPath = computed(() => {
  const folder = pushFolderName.value || 'root'
  const file = pushFilename.value.trim() || 'document.xml'
  return `${folder}/${file}`
})

const warningsAcknowledged = ref(false)

const pushWarningsTruncated = computed(
  () => props.gitPushWarningCount > props.gitPushWarnings.length,
)

const pushWarningsHeading = computed(() => {
  const count = props.gitPushWarningCount || props.gitPushWarnings.length
  return `Перед отправкой в Git: ${formatWarnings(count)}`
})

const pushSubmitDisabled = computed(() => {
  if (!pushFilename.value.trim() || props.gitPushSubmitting) return true
  if (props.gitPushWarnings.length && !warningsAcknowledged.value) return true
  return false
})

const pushSubmitLabel = computed(() => {
  if (props.gitPushSubmitting) {
    return props.gitPushWarnings.length ? 'Отправка…' : 'Проверка…'
  }
  if (props.gitPushWarnings.length) return 'Отправить всё равно'
  return 'Отправить'
})

function defaultPushFilename() {
  const peeked = peekXmlRootElement(editor?.getValue() ?? props.modelValue)
  if (peeked) return `${peeked}.xml`
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

function isFullDocumentPaste(range) {
  const model = editor?.getModel()
  if (!model || !range) return false
  const full = model.getFullModelRange()
  return (
    range.startLineNumber === 1 &&
    range.startColumn === 1 &&
    range.endLineNumber === full.endLineNumber &&
    range.endColumn === full.endColumn
  )
}

function onEditorPaste(e) {
  schedulePasteFlush()
  if (!isFullDocumentPaste(e?.range)) return
  const text = editor.getValue()
  if (text?.trim()) emit('document-paste', text)
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
    fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
    tabSize: 2,
    glyphMargin: true,
    scrollBeyondLastLine: false,
    automaticLayout: true,
  })

  editor.onDidChangeModelContent(onModelContentChanged)
  editor.onDidPaste(onEditorPaste)
  editor.onDidChangeCursorSelection(() => {
    hasSelection.value = !editor.getSelection()?.isEmpty()
  })
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

    const lineCount = model.getLineCount()
    const markers = errors.map((err) => {
      const line = err.line > 0 && err.line <= lineCount ? err.line : 1
      const startCol = err.column > 0 ? err.column : 1
      const lineContent = model.getLineContent(line) || ''
      const endCol = line === err.line && err.column > 0
        ? Math.min(startCol + lineContent.length, 9999)
        : 9999
      return {
        severity: monaco.MarkerSeverity.Error,
        startLineNumber: line,
        startColumn: startCol,
        endLineNumber: line,
        endColumn: endCol,
        message: err.message,
      }
    })

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

function replaceSelection(transform) {
  if (!editor) return
  const selection = editor.getSelection()
  const model = editor.getModel()
  if (!selection?.isEmpty() && model) {
    const text = model.getValueInRange(selection)
    editor.executeEdits('xml-text-transform', [{
      range: selection,
      text: transform(text),
      forceMoveMarkers: true,
    }])
    notifyContentChange()
  }
}

function escapeSelection() {
  replaceSelection(escapeXmlText)
}

function unescapeSelection() {
  replaceSelection(unescapeXmlText)
}

function clearAttributesInSelection() {
  replaceSelection(clearAttributeValues)
}

function closeMoreMenu() {
  moreOpen.value = false
}

function toggleMoreMenu() {
  moreOpen.value = !moreOpen.value
}

function onMoreEscape() {
  escapeSelection()
  closeMoreMenu()
}

function onMoreUnescape() {
  unescapeSelection()
  closeMoreMenu()
}

function onMoreCompare() {
  emit('run-compare')
  closeMoreMenu()
}

function onMoreGitPush() {
  onGitPushClick()
  closeMoreMenu()
}

function onMoreShare() {
  onShareClick()
  closeMoreMenu()
}

onClickOutside(moreRef, closeMoreMenu)

function clearEditor() {
  if (!props.modelValue) return
  emit('clear')
}

function onGitPushClick() {
  pushFilename.value = defaultPushFilename()
  pushCommitMessage.value = ''
  warningsAcknowledged.value = false
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
  if (props.gitPushWarnings.length && !warningsAcknowledged.value) return
  emit('push-to-git', {
    filename,
    commitMessage: pushCommitMessage.value.trim(),
    acknowledgeWarnings: props.gitPushWarnings.length > 0 && warningsAcknowledged.value,
  })
}

watch(
  () => props.gitPushMessage,
  (message) => {
    if (message) showPushDialog.value = true
  },
)

watch(
  () => props.gitPushWarnings,
  () => {
    warningsAcknowledged.value = false
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

.editor-actions .btn-tint-danger {
  background: color-mix(in srgb, var(--danger) 12%, var(--surface2));
  border-color: color-mix(in srgb, var(--danger) 34%, var(--border));
}
.editor-actions .btn-tint-danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--danger) 20%, var(--surface2));
  border-color: color-mix(in srgb, var(--danger) 44%, var(--border));
}

.more-dropdown {
  position: relative;
}

.more-dropdown-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.more-dropdown-chevron {
  font-size: 10px;
  color: var(--text-muted);
  transition: transform 0.15s;
}

.more-dropdown-trigger.open .more-dropdown-chevron {
  transform: rotate(180deg);
}

.more-dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 20;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--text) 12%, transparent);
}

.more-dropdown-item {
  display: block;
  width: 100%;
  padding: 6px 10px;
  font-size: 13px;
  text-align: left;
  color: var(--text);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.more-dropdown-item:hover:not(:disabled) {
  background: color-mix(in srgb, var(--border) 30%, transparent);
}

.more-dropdown-item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.format-icon {
  font-family: var(--font-mono);
  font-weight: 600;
  margin-right: 4px;
}

.import-error {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--danger, #ef4444);
}

.editor-stage {
  position: relative;
  flex: 1;
  min-height: 0;
}

.editor-container {
  flex: 1;
  height: 100%;
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

.push-dialog {
  width: min(460px, 92vw);
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
  font-family: var(--font-mono);
  font-size: 11px;
}

.push-overwrite-hint,
.push-fill-hint {
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
  white-space: pre-wrap;
}

.push-feedback-success {
  color: var(--success, #22c55e);
}

.push-warnings {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--warning) 40%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--warning) 12%, transparent);
}

.push-warnings-heading {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--warning);
}

.push-warnings-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 160px;
  overflow: auto;
}

.push-warnings-list li {
  font-size: 12px;
  line-height: 1.4;
  color: var(--warning);
}

.push-warnings-more {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.push-warnings-ack {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text);
  cursor: pointer;
}

.push-warnings-ack input[type="checkbox"] {
  width: 14px;
  height: 14px;
  min-width: 14px;
  max-width: 14px;
  margin: 1px 0 0;
  padding: 0;
  flex-shrink: 0;
  background: transparent;
  border: none;
  accent-color: var(--accent);
}

.push-warnings-ack span {
  flex: 1;
  min-width: 0;
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
