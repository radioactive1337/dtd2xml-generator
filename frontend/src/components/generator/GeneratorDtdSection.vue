<template>
  <div class="dtd-wrapper card">
    <div class="dtd-collapse-header" @click="$emit('toggle-collapse')">
      <div class="dtd-header-main">
        <span class="panel-title">Схема DTD</span>
        <span v-if="schemaId && collapsed" class="dtd-header-status">
          ✓ {{ fileName }} · {{ elementCountLabel }}
        </span>
      </div>
      <span class="collapse-arrow" :class="{ rotated: collapsed }">▼</span>
    </div>
    <div v-show="!collapsed">
      <DtdUpload
        :is-loaded="!!schemaId"
        :file-name="fileName"
        :element-count="elementCount"
        @uploaded="$emit('uploaded', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import DtdUpload from '../DtdUpload.vue'

defineProps({
  schemaId: { type: String, default: '' },
  collapsed: { type: Boolean, default: false },
  fileName: { type: String, default: '' },
  elementCount: { type: Number, default: 0 },
  elementCountLabel: { type: String, default: '' },
})

defineEmits(['toggle-collapse', 'uploaded'])
</script>

<style scoped>
.dtd-wrapper {
  flex-shrink: 0;
}

.dtd-collapse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: 2px 0 8px;
  user-select: none;
}

.dtd-header-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.dtd-header-status {
  font-size: 12px;
  color: var(--success);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dtd-collapse-header:hover .panel-title {
  color: var(--text);
}

.dtd-collapse-header .panel-title {
  margin-bottom: 0;
  transition: color 0.15s;
}

.collapse-arrow {
  font-size: 11px;
  color: var(--text-muted);
  transition: transform 0.2s ease, color 0.15s;
}

.collapse-arrow.rotated {
  transform: rotate(-90deg);
}
</style>
