<template>
  <div class="left-sticky-footer">
    <div class="action-row">
      <button class="btn-primary" :disabled="!canGenerate || generating" @click="$emit('generate')">
        {{ generating ? 'Генерация…' : 'Сгенерировать XML' }}
      </button>
      <button
        class="btn-secondary"
        :disabled="!xmlText || filling || hasMappingBlockers"
        @click="$emit('fill')"
      >
        {{ filling ? 'Заполнение…' : 'Заполнить данными' }}
      </button>
      <button class="btn-secondary" :disabled="!canValidate || validating" @click="$emit('validate')">
        {{ validating ? 'Проверка…' : 'Проверить по DTD' }}
      </button>
    </div>

    <div v-if="filling" class="fill-progress" role="status" aria-live="polite">
      <div class="fill-progress-header">
        <span class="fill-spinner" aria-hidden="true" />
        <span class="fill-status">{{ fillStatusMessage }}</span>
        <span class="fill-elapsed">{{ fillElapsedLabel }}</span>
      </div>
      <div class="fill-progress-bar" aria-hidden="true">
        <div class="fill-progress-fill" :style="{ width: fillPercent + '%' }" />
      </div>
    </div>

    <p v-if="validationResult?.valid" class="validation-msg valid">XML соответствует DTD</p>
    <p v-if="error" class="error-msg">{{ error }}</p>
  </div>
</template>

<script setup>
defineProps({
  canGenerate: { type: Boolean, default: false },
  generating: { type: Boolean, default: false },
  xmlText: { type: String, default: '' },
  filling: { type: Boolean, default: false },
  hasMappingBlockers: { type: Boolean, default: false },
  canValidate: { type: Boolean, default: false },
  validating: { type: Boolean, default: false },
  fillStatusMessage: { type: String, default: '' },
  fillPercent: { type: Number, default: 0 },
  fillElapsedLabel: { type: String, default: '' },
  validationResult: { type: Object, default: null },
  error: { type: String, default: '' },
})

defineEmits(['generate', 'fill', 'validate'])
</script>

<style scoped>
.left-sticky-footer {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;
  margin-top: 4px;
  border-top: 1px solid var(--border);
}

.action-row {
  display: flex;
  gap: 8px;
}

.fill-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}

.fill-progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.fill-spinner {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  border: 2px solid color-mix(in srgb, var(--accent) 20%, var(--border));
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: fill-spin 0.75s linear infinite;
}

@keyframes fill-spin {
  to { transform: rotate(360deg); }
}

.fill-status {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text);
}

.fill-elapsed {
  flex-shrink: 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

.fill-progress-bar {
  height: 4px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 15%, var(--border));
  overflow: hidden;
}

.fill-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
  transition: width 0.35s ease;
}

.validation-msg.valid {
  font-size: 13px;
  color: var(--success);
  margin: 0;
}

.error-msg {
  font-size: 12px;
  color: var(--danger);
  margin: 0;
}
</style>
