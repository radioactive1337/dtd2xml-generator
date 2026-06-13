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
        accept=".dtd,.ent,.mod"
        style="display: none"
        @change="onFileSelect"
      />
      <template v-if="loading">
        <span class="drop-text">Parsing DTD...</span>
      </template>
      <template v-else-if="isLoaded">
        <span class="drop-icon">✓</span>
        <span class="drop-text">{{ fileName }}</span>
        <span class="drop-sub">{{ elementCount }} elements loaded</span>
      </template>
      <template v-else>
        <span class="drop-icon">↑</span>
        <span class="drop-text">Drop DTD file here or click to browse</span>
        <span class="drop-sub">.dtd, .ent, .mod</span>
      </template>
    </div>
    <p v-if="error" class="error-msg">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { uploadDtd } from '../api/dtd'

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

async function processFile(file) {
  if (!file) return
  loading.value = true
  error.value = ''
  try {
    const result = await uploadDtd(file)
    emit('uploaded', result)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function onDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer.files[0]
  processFile(file)
}

function onFileSelect(e) {
  const file = e.target.files[0]
  processFile(file)
}
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
  background: rgba(59, 130, 246, 0.05);
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
</style>
