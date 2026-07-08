<template>
  <div class="dtd-upload">
    <div
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
        <span v-if="nexusMetaText" class="drop-sub">{{ nexusMetaText }}</span>
      </template>
      <template v-else>
        <span class="drop-icon">↑</span>
        <span class="drop-text">Перетащите DTD или JAR сюда или нажмите для выбора</span>
        <span class="drop-sub">до 3 .dtd или один .jar</span>
      </template>
    </div>
    <button
      v-if="nexusConfigured"
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
import { onMounted, ref } from 'vue'
import { getNexusConfig, pullDtdFromNexus, uploadDtd, uploadDtdJar } from '../api/dtd'
import { normalizeDtdUploadResult } from '../utils/dtdSchema'

defineProps({
  isLoaded: { type: Boolean, default: false },
  fileName: { type: String, default: '' },
  elementCount: { type: Number, default: 0 },
})

const emit = defineEmits(['uploaded'])

const fileInput = ref(null)
const isDragging = ref(false)
const loading = ref(false)
const error = ref('')
const nexusConfigured = ref(false)
const nexusArtifactId = ref('')
const nexusVersion = ref('')
const nexusMetaText = ref('')

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

async function processFiles(fileList) {
  if (!fileList?.length) return
  loading.value = true
  error.value = ''
  nexusMetaText.value = ''
  try {
    const selection = collectUploadFiles(fileList)
    if (!selection) return

    const result =
      selection.kind === 'jar'
        ? await uploadDtdJar(selection.files[0])
        : await uploadDtd(selection.files)
    emit('uploaded', normalizeDtdUploadResult(result))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function refreshFromNexus() {
  loading.value = true
  error.value = ''
  try {
    const result = await pullDtdFromNexus()
    emit('uploaded', normalizeDtdUploadResult(result))
    if (nexusArtifactId.value) {
      const versionLabel = nexusVersion.value || 'LATEST'
      nexusMetaText.value = `Источник: Nexus ${nexusArtifactId.value}:${versionLabel}`
    }
  } catch (e) {
    error.value = e.message
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

onMounted(async () => {
  try {
    const cfg = await getNexusConfig()
    nexusConfigured.value = !!cfg?.configured
    nexusArtifactId.value = cfg?.artifact_id || ''
    nexusVersion.value = cfg?.version || ''
  } catch (_e) {
    nexusConfigured.value = false
  }
})
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
