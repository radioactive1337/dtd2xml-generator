<template>
  <div class="tree-view card">
    <DtdTreePresetsBar
      v-model:preset-name="presetName"
      v-model:load-preset-name="loadPresetName"
      :presets="presets"
      @save="savePreset"
      @load="onLoadPreset"
      @share="openShareDialog"
    />

    <div class="scroller-wrap">
      <RecycleScroller
        ref="scrollerRef"
        v-show="flatNodes.length && !loading"
        class="scroller"
        :items="flatNodes"
        :item-size="32"
        key-field="id"
        v-slot="{ item }"
      >
        <DtdTreeRow
          :key="item.id"
          :item="item"
          :highlighted-path="highlightedPath"
          :element-docs="elementDocs"
          @toggle-expand="toggleExpand"
          @toggle-check="toggleCheck"
        />
      </RecycleScroller>

      <div v-if="loading || !flatNodes.length" class="scroller-hint">
        <template v-if="loading">
          <span class="tree-spinner" aria-hidden="true" />
          <span>{{ loadingMessage }}</span>
        </template>
        <template v-else>
          {{
            rootElement
              ? 'Построение дерева…'
              : 'Выберите корневой элемент или загрузите пресет.'
          }}
        </template>
      </div>
    </div>

    <ShareDocumentDialog
      :open="shareDialogOpen"
      dialog-title="Поделиться пресетом генерации"
      item-label-prefix="Пресет"
      :document-label="sharePresetName"
      :submitting="shareDialogSubmitting"
      :error-message="shareDialogError"
      @close="closeShareDialog"
      @submit="handleShareSubmit"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import DtdTreePresetsBar from './dtd-tree/DtdTreePresetsBar.vue'
import DtdTreeRow from './dtd-tree/DtdTreeRow.vue'
import ShareDocumentDialog from './generator/ShareDocumentDialog.vue'
import { sharePreset } from '../api/presets'
import { translateApiError } from '../utils/apiErrors'
import { useDtdTree } from '../composables/useDtdTree'

const props = defineProps({
  schemaId: { type: String, required: true },
  rootElement: { type: String, default: '' },
  elementDocs: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:paths', 'update:rootElement'])

const {
  flatNodes,
  scrollerRef,
  highlightedPath,
  loading,
  loadingMessage,
  presetName,
  loadPresetName,
  presets,
  toggleExpand,
  toggleCheck,
  savePreset,
  onLoadPreset,
  applyXmlElementPaths,
  revealElement,
} = useDtdTree(props, emit)

const shareDialogOpen = ref(false)
const sharePresetName = ref('')
const shareDialogSubmitting = ref(false)
const shareDialogError = ref('')

function openShareDialog(name) {
  sharePresetName.value = name
  shareDialogError.value = ''
  shareDialogOpen.value = true
}

function closeShareDialog() {
  if (shareDialogSubmitting.value) return
  shareDialogOpen.value = false
  shareDialogError.value = ''
}

async function handleShareSubmit({ recipientUsername, message }) {
  shareDialogSubmitting.value = true
  shareDialogError.value = ''
  try {
    await sharePreset({
      recipientUsername,
      sourcePresetName: sharePresetName.value,
      message,
    })
    shareDialogOpen.value = false
  } catch (err) {
    const detail = err?.response?.data?.detail
    if (detail && typeof detail === 'object') {
      shareDialogError.value = translateApiError(detail.message || 'Пользователь не найден')
    } else {
      shareDialogError.value = translateApiError(detail || err?.message || String(err))
    }
  } finally {
    shareDialogSubmitting.value = false
  }
}

defineExpose({ applyXmlElementPaths, revealElement })
</script>

<style scoped>
.tree-view {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  overflow: hidden;
}

.scroller-wrap {
  flex: 1 1 auto;
  min-height: 360px;
  min-width: 0;
  position: relative;
}

.scroller {
  height: 100%;
  width: 100%;
  min-width: 0;
  min-height: 0;
}

.scroller :deep(.vue-recycle-scroller__item-wrapper) {
  overflow: hidden;
}

.scroller :deep(.vue-recycle-scroller__item-view) {
  overflow: hidden;
  box-sizing: border-box;
}

.scroller-hint {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 13px;
}

.tree-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid color-mix(in srgb, var(--accent) 20%, var(--border));
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: tree-spin 0.75s linear infinite;
}

@keyframes tree-spin {
  to { transform: rotate(360deg); }
}
</style>
