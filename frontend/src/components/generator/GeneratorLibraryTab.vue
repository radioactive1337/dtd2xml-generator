<template>
  <div class="tab-pane library-tab">
    <XmlLibraryPanel
      :active-scope="libraryActiveScope"
      :shared-categories="sharedCategories"
      :personal-documents="personalDocuments"
      :sync-status="syncStatus"
      :syncing="librarySyncing"
      :loading="libraryLoading"
      :library-error="libraryError"
      :can-save="canSaveLibraryDocument"
      :category-documents="categoryDocuments"
      :loading-category="loadingCategory"
      :elements="elements"
      :element-docs="elementDocs"
      :root-element="rootElement"
      @update:active-scope="$emit('update:library-active-scope', $event)"
      @sync="$emit('library-sync')"
      @expand-category="(cat) => $emit('library-expand-category', cat)"
      @open-shared="(cat, id) => $emit('library-open-shared', cat, id)"
      @open-personal="(name) => $emit('library-open-personal', name)"
      @delete-personal="(name) => $emit('library-delete-personal', name)"
      @save="(payload) => $emit('library-save', payload)"
    />
  </div>
</template>

<script setup>
import XmlLibraryPanel from './XmlLibraryPanel.vue'

defineProps({
  libraryActiveScope: { type: String, default: 'shared' },
  sharedCategories: { type: Array, default: () => [] },
  personalDocuments: { type: Array, default: () => [] },
  syncStatus: { type: Object, default: null },
  librarySyncing: { type: Boolean, default: false },
  libraryLoading: { type: Boolean, default: false },
  libraryError: { type: String, default: '' },
  canSaveLibraryDocument: { type: Boolean, default: false },
  categoryDocuments: { type: Object, default: () => ({}) },
  loadingCategory: { type: String, default: null },
  elements: { type: Array, default: () => [] },
  elementDocs: { type: Object, default: () => ({}) },
  rootElement: { type: String, default: '' },
})

defineEmits([
  'update:library-active-scope',
  'library-sync',
  'library-expand-category',
  'library-open-shared',
  'library-open-personal',
  'library-delete-personal',
  'library-save',
])
</script>

<style scoped>
.library-tab {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
