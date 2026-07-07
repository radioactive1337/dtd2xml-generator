import { ref, computed } from 'vue'
import { analyzeStructure, explainStructure } from '../../api/xmlCompare'
import { translateApiError } from '../../utils/apiErrors'

export function useGeneratorCompare({ getEditorXmlText, xmlEditorRef, llmAlias }) {
  const report = ref(null)
  const comparing = ref(false)
  const compareError = ref('')

  const aiExplanation = ref('')
  const aiLoading = ref(false)
  const aiError = ref('')

  const uniqueRanges = computed(() => report.value?.highlight_ranges || [])
  const hasUniquePaths = computed(() => (report.value?.unique_paths?.length || 0) > 0)

  function resetAiState() {
    aiExplanation.value = ''
    aiError.value = ''
    aiLoading.value = false
  }

  function clearReport() {
    report.value = null
    compareError.value = ''
    resetAiState()
    xmlEditorRef.value?.clearUniqueDecorations?.()
  }

  async function runCompare() {
    const xmlText = getEditorXmlText()?.trim()
    if (!xmlText) {
      compareError.value = 'Редактор XML пуст — нечего сравнивать.'
      report.value = null
      return
    }

    comparing.value = true
    compareError.value = ''
    resetAiState()
    try {
      report.value = await analyzeStructure(xmlText)
    } catch (e) {
      compareError.value = translateApiError(e.message || String(e))
      report.value = null
    } finally {
      comparing.value = false
    }
  }

  async function runExplain() {
    if (!report.value || !hasUniquePaths.value) return

    aiLoading.value = true
    aiError.value = ''
    aiExplanation.value = ''
    try {
      const result = await explainStructure({
        rootElement: report.value.root_element,
        uniquePaths: report.value.unique_paths,
        closest: report.value.closest || null,
        snippets: report.value.snippets || [],
        llmAlias: llmAlias?.value || '',
      })
      aiExplanation.value = result.explanation || ''
    } catch (e) {
      aiError.value = translateApiError(e.message || String(e))
    } finally {
      aiLoading.value = false
    }
  }

  function goToPath(range) {
    if (!range?.start_line) return
    xmlEditorRef.value?.goToPosition(range.start_line, 1)
  }

  return {
    compareReport: report,
    comparing,
    compareError,
    uniqueRanges,
    hasUniquePaths,
    aiExplanation,
    aiLoading,
    aiError,
    runCompare,
    runExplain,
    goToComparePath: goToPath,
    clearCompareReport: clearReport,
  }
}
