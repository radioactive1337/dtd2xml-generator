<template>
  <div class="generator" ref="generatorRef">
    <div class="generator-left" :style="{ width: leftWidth + 'px' }">
      <GeneratorDtdSection
        :schema-id="schemaId"
        :collapsed="dtdCollapsed"
        :file-name="dtdMeta.fileName"
        :element-count="dtdMeta.elementCount"
        :element-count-label="elementCountLabel"
        @toggle-collapse="dtdCollapsed = !dtdCollapsed"
        @uploaded="onDtdUploaded"
      />

      <GeneratorLeftTabs
        v-if="schemaId"
        :tabs="leftTabs"
        :active-tab="activeTab"
        :show-data-badge="showDataBadge"
        :results-tab-badge="resultsTabBadge"
        :results-tab-badge-label="resultsTabBadgeLabel"
        @update:active-tab="activeTab = $event"
        @tab-keydown="onTabKeydown"
      />

      <div v-if="schemaId" class="card controls left-panel-body">
        <div
          class="left-tab-content"
          role="tabpanel"
          :aria-labelledby="`left-tab-${activeTab}`"
        >
          <GeneratorStructureTab
            v-show="activeTab === 'structure'"
            ref="structureTabRef"
            :schema-id="schemaId"
            :elements="elements"
            :element-docs="elementDocs"
            v-model:root-element="rootElement"
            v-model:mode="mode"
            v-model:repeat-count="repeatCount"
            v-model:repeat-overrides="repeatOverrides"
            :repeatable-paths="repeatablePaths"
            v-model:custom-paths="customPaths"
          />

          <GeneratorDataTab
            v-show="activeTab === 'data'"
            v-model:fill-strategy="fillStrategy"
            v-model:llm-alias="llmAlias"
            :llm-aliases="llmAliases"
            :default-llm-alias="defaultLlmAlias"
            v-model:auto-validate-after-fill="autoValidateAfterFill"
            v-model:mapping-preset-name="mappingPresetName"
            v-model:selected-mapping-preset-names="selectedMappingPresetNames"
            :field-overrides="fieldOverrides"
            :is-hybrid-strategy="isHybridStrategy"
            :mapping-presets="mappingPresets"
            :preset-dropdown-label="presetDropdownLabel"
            :sql-mappings="sqlMappings"
            :xml-text="liveXmlText || xmlText"
            :mapping-preview="mappingPreview"
            :mapping-validation="mappingValidation"
            @save-mapping-preset="saveMappingPreset"
            @import-mapping-preset="importMappingPreset"
            @export-mapping-preset="exportMappingPreset"
            @open-mapping-wizard="openMappingWizard"
            @add-field-override="addFieldOverride"
            @remove-field-override="removeFieldOverride"
            @update-field-override="updateFieldOverride"
            @remove-mapping="removeMapping"
            @delete-mapping-preset="deleteMappingPreset"
            @remove-selected-preset="removeSelectedPreset"
          />

          <GeneratorResultsTab
            v-show="activeTab === 'results'"
            :validation-result="validationResult"
            :build-info="buildInfo"
            :xml-sync-hint="xmlSyncHint"
            :history="generationHistory"
            :max-entries="historyMaxEntries"
            @go-to-error="goToValidationError"
            @restore="restoreFromHistory"
            @remove="removeHistoryEntry"
            @clear-history="clearGenerationHistory"
          />

          <GeneratorCompareTab
            v-show="activeTab === 'compare'"
            :report="compareReport"
            :comparing="comparing"
            :compare-error="compareError"
            :has-unique-paths="hasUniquePaths"
            :ai-available="llmAliases.length > 0"
            :ai-explanation="aiExplanation"
            :ai-loading="aiLoading"
            :ai-error="aiError"
            @run-compare="runCompare"
            @run-explain="runExplain"
            @go-to-path="goToComparePath"
          />

          <GeneratorLibraryTab
            v-show="activeTab === 'library'"
            v-model:library-active-scope="libraryActiveScope"
            :shared-categories="sharedCategories"
            :personal-documents="personalDocuments"
            :sync-status="syncStatus"
            :library-syncing="librarySyncing"
            :library-loading="libraryLoading"
            :library-error="libraryError"
            :category-documents="categoryDocuments"
            :loading-category="loadingCategory"
            :elements="elements"
            :element-docs="elementDocs"
            :root-element="rootElement"
            :schema-id="schemaId"
            @library-sync="handleLibrarySync"
            @library-expand-category="handleLibraryExpandCategory"
            @library-open-shared="handleLibraryOpenShared"
            @library-open-personal="handleLibraryOpenPersonal"
            @library-share-personal="openSharePersonalDialog"
            @library-delete-personal="handleLibraryDeletePersonal"
          />
        </div>

        <GeneratorActionFooter
          :can-generate="canGenerate"
          :generating="generating"
          :xml-text="xmlText"
          :filling="filling"
          :has-mapping-blockers="hasMappingBlockers || hasLlmBlocker"
          :can-validate="canValidate"
          :validating="validating"
          :fill-status-message="fillStatusMessage"
          :fill-percent="fillPercent"
          :fill-elapsed-label="fillElapsedLabel"
          :error="error"
          @generate="generate"
          @fill="fill"
          @cancel-fill="cancelFill"
          @validate="validate"
        />
      </div>

      <MappingWizard
        :open="wizardOpen"
        :initial-mapping="wizardInitialMapping"
        :schema-id="schemaId"
        :xml-text="liveXmlText || xmlText"
        :elements="elements"
        :element-docs="elementDocs"
        :element-attribute-docs="elementAttributeDocs"
        :element-attributes="elementAttributes"
        :db-aliases="dbAliases"
        :llm-alias="llmAlias"
        :available-paths="availableElementPaths"
        @close="onWizardClose"
        @finish="onWizardFinish"
      />
    </div>

    <div class="col-divider" @mousedown.prevent="startHResize" title="Потяните для изменения ширины" />

    <div class="generator-right">
      <XmlEditor
        ref="xmlEditorRef"
        :model-value="xmlText"
        :filename="`${rootElement || 'generated'}.xml`"
        :validation-errors="validationResult?.valid === false ? validationResult.errors : []"
        :can-save="canSaveLibraryDocument"
        :unique-ranges="uniqueRanges"
        :git-push-enabled="gitPushEnabled"
        :root-element="rootElement"
        :git-push-submitting="gitPushSubmitting"
        :git-push-message="gitPushMessage"
        :git-push-error="gitPushError"
        @content-change="onEditorContentChange"
        @clear="onEditorClear"
        @import="onXmlFileImported"
        @save="handleLibrarySave"
        @share="openShareInlineDialog"
        @push-to-git="handleGitPush"
        @push-dialog-open="resetGitPushFeedback"
        @push-dialog-close="resetGitPushFeedback"
      />
    </div>

    <ShareDocumentDialog
      :open="shareDialogOpen"
      :document-label="shareDialogMode === 'personal' ? shareDialogDocumentName : ''"
      :require-document-name="shareDialogMode === 'inline'"
      :default-document-name="rootElement || 'document'"
      :submitting="shareDialogSubmitting"
      :error-message="shareDialogError"
      @close="closeShareDialog"
      @submit="handleShareSubmit"
    />
  </div>
</template>

<script setup>
defineOptions({ name: 'GeneratorView' })

import XmlEditor from '../components/XmlEditor.vue'
import MappingWizard from '../components/MappingWizard.vue'
import GeneratorDtdSection from '../components/generator/GeneratorDtdSection.vue'
import GeneratorLeftTabs from '../components/generator/GeneratorLeftTabs.vue'
import GeneratorStructureTab from '../components/generator/GeneratorStructureTab.vue'
import GeneratorDataTab from '../components/generator/GeneratorDataTab.vue'
import GeneratorResultsTab from '../components/generator/GeneratorResultsTab.vue'
import GeneratorCompareTab from '../components/generator/GeneratorCompareTab.vue'
import GeneratorLibraryTab from '../components/generator/GeneratorLibraryTab.vue'
import GeneratorActionFooter from '../components/generator/GeneratorActionFooter.vue'
import ShareDocumentDialog from '../components/generator/ShareDocumentDialog.vue'
import { useGenerator } from '../composables/generator/useGenerator'

const {
  generatorRef,
  structureTabRef,
  xmlEditorRef,
  leftWidth,
  dtdCollapsed,
  startHResize,
  leftTabs,
  schemaId,
  dtdMeta,
  elementCountLabel,
  elements,
  elementDocs,
  elementAttributeDocs,
  elementAttributes,
  rootElement,
  mode,
  repeatCount,
  repeatOverrides,
  repeatablePaths,
  customPaths,
  fillStrategy,
  isHybridStrategy,
  dbAliases,
  llmAliases,
  defaultLlmAlias,
  llmAlias,
  mappingPresetName,
  selectedMappingPresetNames,
  mappingPresets,
  wizardOpen,
  wizardInitialMapping,
  mappingPreview,
  sqlMappings,
  fieldOverrides,
  presetDropdownLabel,
  mappingValidation,
  hasMappingBlockers,
  hasLlmBlocker,
  availableElementPaths,
  xmlText,
  liveXmlText,
  buildInfo,
  generating,
  filling,
  fillStatusMessage,
  fillPercent,
  fillElapsedLabel,
  validating,
  validationResult,
  generationHistory,
  historyMaxEntries,
  activeTab,
  autoValidateAfterFill,
  showDataBadge,
  resultsTabBadge,
  resultsTabBadgeLabel,
  onTabKeydown,
  error,
  xmlSyncHint,
  canGenerate,
  canValidate,
  onDtdUploaded,
  openMappingWizard,
  onWizardClose,
  removeMapping,
  addFieldOverride,
  removeFieldOverride,
  updateFieldOverride,
  saveMappingPreset,
  removeSelectedPreset,
  deleteMappingPreset,
  exportMappingPreset,
  importMappingPreset,
  onWizardFinish,
  goToValidationError,
  onEditorContentChange,
  onEditorClear,
  onXmlFileImported,
  restoreFromHistory,
  removeHistoryEntry,
  clearGenerationHistory,
  libraryActiveScope,
  sharedCategories,
  personalDocuments,
  syncStatus,
  librarySyncing,
  libraryLoading,
  libraryError,
  canSaveLibraryDocument,
  gitPushEnabled,
  gitPushSubmitting,
  gitPushMessage,
  gitPushError,
  resetGitPushFeedback,
  handleGitPush,
  categoryDocuments,
  loadingCategory,
  handleLibrarySync,
  handleLibraryExpandCategory,
  handleLibraryOpenShared,
  handleLibraryOpenPersonal,
  handleLibrarySave,
  handleLibraryDeletePersonal,
  shareDialogOpen,
  shareDialogMode,
  shareDialogDocumentName,
  shareDialogSubmitting,
  shareDialogError,
  openSharePersonalDialog,
  openShareInlineDialog,
  closeShareDialog,
  handleShareSubmit,
  generate,
  fill,
  cancelFill,
  validate,
  compareReport,
  comparing,
  compareError,
  uniqueRanges,
  hasUniquePaths,
  aiExplanation,
  aiLoading,
  aiError,
  runCompare,
  runExplain,
  goToComparePath,
} = useGenerator()
</script>

<style scoped>
.generator {
  display: flex;
  align-items: stretch;
  gap: 0;
  height: 100%;
  flex: 1;
  min-height: 0;
}

.generator-left {
  display: flex;
  flex-direction: column;
  gap: 0;
  flex-shrink: 0;
  min-width: 480px;
  height: 100%;
  overflow: hidden;
}

.left-panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin-top: 0;
  container-type: inline-size;
}

.left-tab-content {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.col-divider {
  width: 8px;
  align-self: stretch;
  cursor: col-resize;
  position: relative;
  flex-shrink: 0;
}

.col-divider::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  transform: translateX(-50%);
  background: var(--border);
  border-radius: 2px;
  transition: background 0.15s;
}

.col-divider:hover::after {
  background: var(--accent);
}

.generator-right {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.controls {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-top: 0;
}

@media (max-width: 900px) {
  .generator {
    flex-direction: column;
  }
  .generator-left {
    width: 100% !important;
  }
  .col-divider {
    display: none;
  }
}
</style>
