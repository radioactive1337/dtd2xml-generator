import { ref, computed, watch } from 'vue'
import { generateXml } from '../../api/generate'
import { fillXmlStream, stageFillXml } from '../../api/fill'
import { validateXml } from '../../api/validate'
import { translateFillStep } from '../../utils/fillProgress'

export function useGeneratorActions({
  schemaId,
  rootElement,
  mode,
  repeatCount,
  repeatOverrides,
  customPaths,
  fillStrategy,
  llmAlias,
  isHybridStrategy,
  sqlMappings,
  fieldOverrides,
  xmlText,
  xmlDirty,
  buildInfo,
  validationResult,
  xmlSyncHint,
  error,
  generating,
  filling,
  validating,
  autoValidateAfterFill,
  getEditorXmlText,
  setProgrammaticXml,
  addHistoryEntry,
  focusResultsTab,
}) {
  const fillStatusMessage = ref('')
  const fillPercent = ref(0)
  const fillElapsedSeconds = ref(0)

  let generateRequestSeq = 0
  let fillElapsedTimer = null
  let fillAbortController = null
  let inlineValidationTimer = null

  const canGenerate = computed(() => schemaId.value && rootElement.value)
  const canValidate = computed(() => schemaId.value && xmlText.value)

  const fillElapsedLabel = computed(() => {
    const seconds = fillElapsedSeconds.value
    if (seconds < 60) return `${seconds}s`
    const minutes = Math.floor(seconds / 60)
    const remainder = seconds % 60
    return `${minutes}m ${remainder}s`
  })

  function startFillProgressTimer() {
    fillElapsedSeconds.value = 0
    clearInterval(fillElapsedTimer)
    fillElapsedTimer = setInterval(() => {
      fillElapsedSeconds.value += 1
    }, 1000)
  }

  function stopFillProgressTimer() {
    clearInterval(fillElapsedTimer)
    fillElapsedTimer = null
  }

  function resetFillProgress() {
    fillStatusMessage.value = ''
    fillPercent.value = 0
    fillElapsedSeconds.value = 0
  }

  async function generate() {
    const requestSeq = ++generateRequestSeq
    generating.value = true
    error.value = ''
    try {
      const config = {
        schema_id: schemaId.value,
        root_element: rootElement.value,
        mode: mode.value,
        repeat_count: repeatCount.value,
        repeat_overrides: repeatOverrides.value,
        custom_paths: mode.value === 'custom' ? customPaths.value : [],
      }
      const result = await generateXml(config)
      if (requestSeq !== generateRequestSeq) return
      await setProgrammaticXml(result.xml_text)
      buildInfo.value = result
      validationResult.value = null
      addHistoryEntry({
        type: 'generate',
        schema_id: schemaId.value,
        root_element: rootElement.value,
        mode: mode.value,
        xml_text: result.xml_text,
        node_count: result.node_count,
        warnings: result.warnings || [],
      })
      if (result.warnings?.length) {
        focusResultsTab()
      }
    } catch (e) {
      if (requestSeq === generateRequestSeq) error.value = e.message
    } finally {
      if (requestSeq === generateRequestSeq) generating.value = false
    }
  }

  async function runValidation() {
    if (!schemaId.value || !xmlText.value) return

    validating.value = true
    error.value = ''
    try {
      validationResult.value = await validateXml(schemaId.value, getEditorXmlText() || xmlText.value)
      if (validationResult.value?.valid === true) {
        xmlSyncHint.value = ''
      } else if (validationResult.value?.valid === false) {
        focusResultsTab()
      }
    } catch (e) {
      error.value = e.message
      validationResult.value = null
    } finally {
      validating.value = false
    }
  }

  function scheduleInlineValidation() {
    if (inlineValidationTimer) clearTimeout(inlineValidationTimer)
    inlineValidationTimer = setTimeout(async () => {
      inlineValidationTimer = null
      if (!schemaId.value || !xmlText.value || generating.value || filling.value) return
      try {
        const result = await validateXml(schemaId.value, getEditorXmlText() || xmlText.value)
        validationResult.value = result
        if (result?.valid === true) xmlSyncHint.value = ''
      } catch {
        // Inline validation failures are silent — errors show up via manual validate
      }
    }, 800)
  }

  watch([xmlText, xmlDirty], ([text, dirty]) => {
    if (!dirty) return
    if (!text) {
      if (inlineValidationTimer) {
        clearTimeout(inlineValidationTimer)
        inlineValidationTimer = null
      }
      return
    }
    scheduleInlineValidation()
  })

  async function fill() {
    filling.value = true
    error.value = ''
    resetFillProgress()
    fillStatusMessage.value = 'Запуск заполнения…'
    startFillProgressTimer()
    fillAbortController = new AbortController()
    let filled = false
    try {
      if (xmlDirty.value) {
        fillStatusMessage.value = 'Загрузка XML…'
        await stageFillXml(schemaId.value, getEditorXmlText() || xmlText.value)
        xmlDirty.value = false
      }

      const request = {
        schema_id: schemaId.value,
        strategy: fillStrategy.value,
      }
      if (llmAlias.value) {
        request.llm_alias = llmAlias.value
      }
      if (isHybridStrategy.value) {
        request.sql_mappings = sqlMappings.value
          .filter((m) => m.query?.trim() && m.target_element?.trim())
          .map((m) => ({
            query: m.query,
            target_element: m.target_element,
            target_path: m.target_path?.trim() || null,
            fields: Object.fromEntries(
              m.fields.filter((f) => f.db_col && f.xml_attr).map((f) => [f.db_col, f.xml_attr]),
            ),
            db_alias: m.db_alias || null,
          }))
      }
      const activeOverrides = fieldOverrides.value
        .filter((o) => o.target_path?.trim() && o.xml_attr?.trim())
        .map(({ _presetSource, ...o }) => ({
          target_path: o.target_path.trim(),
          xml_attr: o.xml_attr.trim(),
          value: o.value ?? '',
          target_element: o.target_element?.trim() || null,
        }))
      if (activeOverrides.length) {
        request.field_overrides = activeOverrides
      }
      const result = await fillXmlStream(
        request,
        ({ step, message, percent }) => {
          const translated = translateFillStep(step)
          if (translated) fillStatusMessage.value = translated
          else if (message) fillStatusMessage.value = message
          if (typeof percent === 'number') fillPercent.value = percent
        },
        { signal: fillAbortController.signal },
      )
      await setProgrammaticXml(result.xml_text)
      xmlDirty.value = false
      filled = true
    } catch (e) {
      if (e.name === 'AbortError') {
        fillStatusMessage.value = translateFillStep('cancelled')
      } else {
        error.value = e.message
      }
    } finally {
      fillAbortController = null
      stopFillProgressTimer()
      filling.value = false
    }
    if (filled) {
      if (autoValidateAfterFill.value) {
        await runValidation()
      } else {
        validationResult.value = null
      }
      addHistoryEntry({
        type: 'fill',
        schema_id: schemaId.value,
        root_element: rootElement.value,
        xml_text: xmlText.value,
        node_count: buildInfo.value?.node_count ?? null,
        warnings: buildInfo.value?.warnings || [],
        validation_valid: validationResult.value?.valid ?? null,
      })
    }
  }

  function cancelFill() {
    fillAbortController?.abort()
  }

  async function validate() {
    await runValidation()
  }

  function dispose() {
    stopFillProgressTimer()
    if (inlineValidationTimer) clearTimeout(inlineValidationTimer)
  }

  return {
    canGenerate,
    canValidate,
    fillStatusMessage,
    fillPercent,
    fillElapsedLabel,
    generate,
    fill,
    cancelFill,
    validate,
    dispose,
  }
}
