<template>
  <div class="dtd-upload">
    <div
      v-if="canUpdate"
      class="drop-zone"
      :class="{ dragging: isDragging, loaded: isLoaded }"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
      @click="fileInput.click()"
    >
      <input
        ref="fileInput"
        type="file"
        accept=".dtd,.jar"
        multiple
        style="display: none"
        @change="onFileSelect"
      />
      <template v-if="loading">
        <span class="drop-text">Разбор DTD…</span>
      </template>
      <template v-else-if="isLoaded">
        <span class="drop-icon">✓</span>
        <span class="drop-text">{{ fileName }}</span>
        <span class="drop-sub">Загружено элементов: {{ elementCount }}</span>
        <span v-if="importSourceLabel" class="drop-sub">{{ importSourceLabel }}</span>
        <span v-if="updatedAtLabel" class="drop-sub">{{ updatedAtLabel }}</span>
      </template>
      <template v-else>
        <span class="drop-icon">↑</span>
        <span class="drop-text">Перетащите DTD или JAR сюда или нажмите для выбора</span>
        <span class="drop-sub">до 3 .dtd или один .jar</span>
      </template>
    </div>
    <div v-else class="drop-zone loaded dtd-readonly">
      <template v-if="isLoaded">
        <span class="drop-icon">✓</span>
        <span class="drop-text">{{ fileName }}</span>
        <span class="drop-sub">Загружено элементов: {{ elementCount }}</span>
        <span v-if="importSourceLabel" class="drop-sub">{{ importSourceLabel }}</span>
        <span v-if="updatedAtLabel" class="drop-sub">{{ updatedAtLabel }}</span>
      </template>
      <template v-else>
        <span class="drop-text">Схема DTD не загружена</span>
        <span class="drop-sub">Обновление схемы доступно только администратору</span>
      </template>
    </div>
    <button
      v-if="canUpdate && nexusConfigured"
      class="nexus-btn"
      :disabled="loading"
      type="button"
      @click="refreshFromNexus"
    >
      Обновить из Nexus
    </button>
    <p v-if="error" class="error-msg">{{ error }}</p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { getNexusConfig, pullDtdFromNexus, uploadDtd, uploadDtdJar } from '../api/dtd'
import { formatDtdUpdatedAt, normalizeDtdUploadResult } from '../utils/dtdSchema'

const props = defineProps({
  canUpdate: { type: Boolean, default: true },
  isLoaded: { type: Boolean, default: false },
  fileName: { type: String, default: '' },
  elementCount: { type: Number, default: 0 },
  importSource: { type: String, default: '' },
  updatedAt: { type: String, default: '' },
  sourceType: { type: String, default: '' },
})

const emit = defineEmits(['uploaded'])

const fileInput = ref(null)
const isDragging = ref(false)
const loading = ref(false)
const error = ref('')
const nexusConfigured = ref(false)

const importSourceLabel = computed(() =>
  props.importSource ? `Источник: ${props.importSource}` : '',
)
const updatedAtLabel = computed(() => {
  const formatted = formatDtdUpdatedAt(props.updatedAt)
  return formatted ? `Обновлено: ${formatted}` : ''
})

const isCustomSource = computed(() => {
  const type = props.sourceType
  if (type) return type !== 'nexus'
  if (!props.importSource) return false
  return !props.importSource.startsWith('Nexus ')
})

function isJarFile(file) {
  return file.name.toLowerCase().endsWith('.jar')
}

function isDtdFile(file) {
  return file.name.toLowerCase().endsWith('.dtd')
}

function collectUploadFiles(fileList) {
  const files = [...fileList]
  if (!files.length) return null

  if (files.length === 1 && isJarFile(files[0])) {
    return { kind: 'jar', files: [files[0]] }
  }

  const dtdFiles = files.filter(isDtdFile)
  if (!dtdFiles.length) {
    throw new Error('Выберите до 3 файлов .dtd или один .jar')
  }
  if (dtdFiles.length > 3) {
    throw new Error('Можно загрузить не более 3 DTD файлов за раз')
  }
  return { kind: 'dtd', files: dtdFiles }
}

function confirmCustomOverwrite() {
  if (!props.isLoaded || !isCustomSource.value) return true
  const source = props.importSource || 'ручная загрузка'
  return window.confirm(
    `Текущая схема DTD загружена не из Nexus (${source}).\n\n` +
      'В ней могут быть локальные или новые фичи. ' +
      'Уточните у коллеги, можно ли заменять схему.\n\n' +
      'Продолжить обновление?',
  )
}

function isCustomOverwriteError(err) {
  const detail = err?.response?.data?.detail
  if (detail && typeof detail === 'object') {
    return detail.code === 'DTD_CUSTOM_OVERWRITE'
  }
  return false
}

function errorMessage(err) {
  const detail = err?.response?.data?.detail
  if (detail && typeof detail === 'object' && detail.message) {
    return detail.message
  }
  return err.message
}

async function processFiles(fileList, { force = false } = {}) {
  if (!fileList?.length) return
  let useForce = force
  if (!useForce && props.isLoaded && isCustomSource.value) {
    if (!confirmCustomOverwrite()) return
    useForce = true
  }

  loading.value = true
  error.value = ''
  try {
    const selection = collectUploadFiles(fileList)
    if (!selection) return

    const options = { force: useForce }
    const result =
      selection.kind === 'jar'
        ? await uploadDtdJar(selection.files[0], options)
        : await uploadDtd(selection.files, options)
    emit('uploaded', normalizeDtdUploadResult(result))
  } catch (e) {
    if (!useForce && isCustomOverwriteError(e) && confirmCustomOverwrite()) {
      loading.value = false
      await processFiles(fileList, { force: true })
      return
    }
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function refreshFromNexus({ force = false } = {}) {
  let useForce = force
  if (!useForce && props.isLoaded && isCustomSource.value) {
    if (!confirmCustomOverwrite()) return
    useForce = true
  }

  loading.value = true
  error.value = ''
  try {
    const result = await pullDtdFromNexus({ force: useForce })
    emit('uploaded', normalizeDtdUploadResult(result))
  } catch (e) {
    if (!useForce && isCustomOverwriteError(e) && confirmCustomOverwrite()) {
      loading.value = false
      await refreshFromNexus({ force: true })
      return
    }
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

function onDrop(e) {
  isDragging.value = false
  processFiles(e.dataTransfer.files)
}

function onFileSelect(e) {
  processFiles(e.target.files)
  e.target.value = ''
}

watch(
  () => props.canUpdate,
  async (canUpdate) => {
    if (!canUpdate) {
      nexusConfigured.value = false
      return
    }
    try {
      const cfg = await getNexusConfig()
      nexusConfigured.value = !!cfg?.configured
    } catch (_e) {
      nexusConfigured.value = false
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.drop-zone {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.drop-zone:hover,
.drop-zone.dragging {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 5%, transparent);
}

.drop-zone.loaded {
  border-color: var(--success);
  border-style: solid;
}

.dtd-readonly {
  cursor: default;
}

.drop-icon {
  font-size: 24px;
  color: var(--accent);
}

.drop-zone.loaded .drop-icon {
  color: var(--success);
}

.drop-text {
  font-size: 14px;
  font-weight: 500;
}

.drop-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.nexus-btn {
  margin-top: 10px;
  width: 100%;
}
</style>
