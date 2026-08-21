<template>
  <div class="dtd-wrapper card">
    <div class="dtd-collapse-header" @click="$emit('toggle-collapse')">
      <div class="dtd-header-main">
        <span class="panel-title">Схема DTD</span>
        <div v-if="schemaId && collapsed" class="dtd-header-status">
          <span class="dtd-header-status-primary">
            ✓ {{ fileName }} · {{ elementCountLabel }}
          </span>
          <span v-if="importSourceLabel" class="dtd-header-status-line">
            {{ importSourceLabel }}
          </span>
          <span v-if="updatedAtLabel" class="dtd-header-status-line">
            {{ updatedAtLabel }}
          </span>
        </div>
      </div>
      <span class="collapse-arrow" :class="{ rotated: collapsed }">▼</span>
    </div>
    <div v-show="!collapsed">
      <DtdUpload
        :can-update="canUpdateDtd"
        :is-loaded="!!schemaId"
        :file-name="fileName"
        :element-count="elementCount"
        :import-source="importSource"
        :updated-at="updatedAt"
        :source-type="sourceType"
        @uploaded="$emit('uploaded', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DtdUpload from '../DtdUpload.vue'
import { formatDtdUpdatedAt } from '../../utils/dtdSchema'

const props = defineProps({
  canUpdateDtd: { type: Boolean, default: false },
  schemaId: { type: String, default: '' },
  collapsed: { type: Boolean, default: false },
  fileName: { type: String, default: '' },
  elementCount: { type: Number, default: 0 },
  elementCountLabel: { type: String, default: '' },
  importSource: { type: String, default: '' },
  updatedAt: { type: String, default: '' },
  sourceType: { type: String, default: '' },
})

defineEmits(['toggle-collapse', 'uploaded'])

const importSourceLabel = computed(() =>
  props.importSource ? `Источник: ${props.importSource}` : '',
)
const updatedAtLabel = computed(() => {
  const formatted = formatDtdUpdatedAt(props.updatedAt)
  return formatted ? `обновлено ${formatted}` : ''
})
</script>

<style scoped>
.dtd-wrapper {
  flex-shrink: 0;
}

.dtd-collapse-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  cursor: pointer;
  padding: 2px 0 8px;
  user-select: none;
}

.dtd-header-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.dtd-header-status {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  font-size: 12px;
  color: var(--success);
  font-weight: 500;
}

.dtd-header-status-primary,
.dtd-header-status-line {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.dtd-collapse-header:hover .panel-title {
  color: var(--text);
}

.dtd-collapse-header .panel-title {
  margin-bottom: 0;
  transition: color 0.15s;
}

.collapse-arrow {
  flex-shrink: 0;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
  transition: transform 0.2s ease, color 0.15s;
}

.collapse-arrow.rotated {
  transform: rotate(-90deg);
}
</style>
