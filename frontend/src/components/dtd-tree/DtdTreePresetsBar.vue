<template>
  <div class="tree-header">
    <div class="panel-title">Дерево (свой режим)</div>
    <div class="tree-actions">
      <input
        :value="presetName"
        placeholder="Имя пресета"
        class="preset-input"
        @input="emit('update:presetName', $event.target.value)"
      />
      <button class="btn-secondary" :disabled="!presetName" @click="emit('save')">
        Сохранить
      </button>
      <select
        :value="loadPresetName"
        class="preset-select"
        @change="onPresetSelect"
      >
        <option value="">Выберите пресет…</option>
        <option v-for="p in presets" :key="p.name" :value="p.name">
          {{ p.name }}{{ p.shared_by_name ? ` (от ${p.shared_by_name})` : '' }}
        </option>
      </select>
      <button
        class="btn-secondary"
        :disabled="!loadPresetName"
        title="Поделиться пресетом"
        @click="emit('share', loadPresetName)"
      >
        Поделиться
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  presetName: { type: String, default: '' },
  loadPresetName: { type: String, default: '' },
  presets: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:presetName', 'update:loadPresetName', 'save', 'load', 'share'])

function onPresetSelect(event) {
  const value = event.target.value
  emit('update:loadPresetName', value)
  if (value) emit('load')
}
</script>

<style scoped>
.tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.tree-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.preset-input { width: 140px; }
.preset-select { width: 180px; }
</style>
