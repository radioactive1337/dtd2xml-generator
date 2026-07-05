<template>
  <div class="tab-pane structure-tab">
    <div class="field">
      <label>Корневой элемент</label>
      <ElementPicker
        :model-value="rootElement"
        :elements="elements"
        :element-docs="elementDocs"
        placeholder="Имя элемента (введите или выберите из списка)"
        @update:model-value="$emit('update:rootElement', $event)"
      />
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
      <div class="field tree-search-field">
        <label>Найти элемент</label>
        <ElementPicker
          v-model="treeSearchQuery"
          :elements="elements"
          :element-docs="elementDocs"
          placeholder="Имя элемента (введите или выберите из списка)"
          @confirm="onTreeSearch"
        />
        <p v-if="treeSearchError" class="tree-search-error">{{ treeSearchError }}</p>
      </div>
      <DtdTreeView
        ref="dtdTreeRef"
        :schema-id="schemaId"
        :root-element="rootElement"
        :element-docs="elementDocs"
        @update:paths="$emit('update:customPaths', $event)"
        @update:root-element="$emit('update:rootElement', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import DtdTreeView from '../DtdTreeView.vue'
import ElementPicker from '../ElementPicker.vue'
import { resolveElementName } from '../../utils/elementFilter'

const props = defineProps({
  schemaId: { type: String, required: true },
  rootElement: { type: String, default: '' },
  elements: { type: Array, default: () => [] },
  elementDocs: { type: Object, default: () => ({}) },
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
const treeSearchQuery = ref('')
const treeSearchError = ref('')

watch(
  () => [props.schemaId, props.rootElement],
  () => {
    treeSearchQuery.value = ''
    treeSearchError.value = ''
  },
)

async function onTreeSearch(name) {
  treeSearchError.value = ''
  const target = resolveElementName(name, props.elements)
  if (!target) return

  const result = await dtdTreeRef.value?.revealElement(target)
  if (!result?.ok) {
    treeSearchError.value = result?.error || 'Элемент не найден в дереве'
  }
}

defineExpose({ dtdTreeRef })
</script>

<style scoped>
.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.structure-tab {
  min-height: 0;
  min-width: 0;
  height: 100%;
  overflow: hidden;
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

.tree-search-field {
  flex-shrink: 0;
}

.tree-search-error {
  font-size: 11px;
  color: var(--danger);
  margin: 0;
}

.structure-tree-host {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.structure-tree-host :deep(.tree-view) {
  flex: 1 1 0;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.structure-tree-host :deep(.scroller-wrap) {
  flex: 1 1 auto;
  min-height: 240px;
  min-width: 0;
}
</style>
