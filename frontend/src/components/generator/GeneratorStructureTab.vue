<template>
  <div class="tab-pane structure-tab">
    <div class="field">
      <label>Корневой элемент</label>
      <input
        :value="rootElement"
        :list="datalistListFor('root', 'root-elements-list')"
        placeholder="Имя элемента (введите или выберите из списка)"
        @input="$emit('update:rootElement', $event.target.value)"
        @focus="openDatalist('root')"
        @blur="scheduleCloseDatalist('root')"
        @change="onRootElementChange"
        @keydown.enter="onDatalistEnter($event, 'root')"
      />
      <datalist id="root-elements-list">
        <option v-for="el in elements" :key="el" :value="el" />
      </datalist>
    </div>

    <div class="field">
      <label>Режим сборки</label>
      <div class="mode-group">
        <label v-for="m in modes" :key="m.value" class="mode-label">
          <input
            type="radio"
            :checked="mode === m.value"
            @change="$emit('update:mode', m.value)"
          />
          {{ m.label }}
        </label>
      </div>
    </div>

    <div v-if="mode === 'maximal' || mode === 'custom'" class="field">
      <label>Число повторов (+ / *)</label>
      <input
        :value="repeatCount"
        type="number"
        min="1"
        max="100"
        @input="$emit('update:repeatCount', Number($event.target.value))"
      />
    </div>

    <div v-if="mode === 'custom'" class="structure-tree-host">
      <DtdTreeView
        ref="dtdTreeRef"
        :schema-id="schemaId"
        :root-element="rootElement"
        @update:paths="$emit('update:customPaths', $event)"
        @update:root-element="$emit('update:rootElement', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import DtdTreeView from '../DtdTreeView.vue'
import {
  datalistListFor,
  openDatalist,
  scheduleCloseDatalist,
  confirmDatalistPick,
  isOptionSelected,
} from '../../utils/datalistInput'

const props = defineProps({
  schemaId: { type: String, required: true },
  rootElement: { type: String, default: '' },
  elements: { type: Array, default: () => [] },
  mode: { type: String, default: 'minimal' },
  repeatCount: { type: Number, default: 1 },
})

defineEmits(['update:rootElement', 'update:mode', 'update:repeatCount', 'update:customPaths'])

const modes = [
  { value: 'minimal', label: 'Минимальный' },
  { value: 'maximal', label: 'Максимальный' },
  { value: 'custom', label: 'Свой' },
]

const dtdTreeRef = ref(null)
defineExpose({ dtdTreeRef })

function onDatalistEnter(event, key) {
  confirmDatalistPick(key)
  event.target.blur()
}

function onRootElementChange(event) {
  const input = event.target
  if (!input.value || isOptionSelected(input, props.elements)) {
    confirmDatalistPick('root')
  }
}
</script>

<style scoped>
.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.structure-tab {
  min-height: 0;
  height: 100%;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mode-group {
  display: flex;
  gap: 12px;
}

.mode-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: var(--text);
  cursor: pointer;
}

.structure-tree-host {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.structure-tree-host :deep(.tree-view) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.structure-tree-host :deep(.scroller-wrap) {
  flex: 1;
  min-height: min(360px, 50vh);
  height: auto;
}
</style>
