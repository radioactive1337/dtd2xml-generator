<template>
  <div class="tab-pane">
    <div v-if="status" class="results-status" :class="`results-status--${status}`" role="status">
      <span class="results-status-dot" aria-hidden="true" />
      <span>{{ statusMessage }}</span>
    </div>

    <ul v-if="validationResult?.valid === false && validationResult?.errors?.length" class="validation-errors">
      <li v-for="(err, i) in validationResult.errors" :key="i">
        <button
          v-if="err.line"
          type="button"
          class="validation-error-link"
          @click="$emit('go-to-error', err)"
        >
          Строка {{ err.line }}, столбец {{ err.column }}: {{ err.message }}
        </button>
        <span v-else>{{ err.message }}</span>
      </li>
    </ul>

    <p v-if="buildInfo" class="build-info">
      {{ nodesLabel }}
    </p>

    <template v-if="buildInfo?.warnings?.length">
      <p class="build-warnings-heading">
        {{ warningsHeading }}
      </p>
      <ul class="build-warnings">
        <li v-for="(warning, i) in buildInfo.warnings" :key="i">{{ warning }}</li>
      </ul>
    </template>

    <p v-if="xmlSyncHint && status !== 'error'" class="error-msg">{{ xmlSyncHint }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatErrors, formatNodes, formatWarnings } from '../../utils/ruPlural'

const props = defineProps({
  validationResult: { type: Object, default: null },
  buildInfo: { type: Object, default: null },
  xmlSyncHint: { type: String, default: '' },
})

defineEmits(['go-to-error'])

const status = computed(() => {
  if (props.validationResult?.valid === false && props.validationResult?.errors?.length) return 'error'
  if (props.validationResult?.valid === true) return 'ok'
  if (props.xmlSyncHint) return 'error'
  if (props.buildInfo?.warnings?.length) return 'warn'
  if (props.buildInfo && !props.buildInfo.warnings?.length) return 'ok'
  return null
})

const nodesLabel = computed(() => {
  if (!props.buildInfo) return ''
  return formatNodes(props.buildInfo.node_count)
})

const warningsHeading = computed(() => {
  const count = props.buildInfo?.warnings?.length ?? 0
  return `${formatWarnings(count)}:`
})

const statusMessage = computed(() => {
  if (status.value === 'error') {
    if (props.validationResult?.valid === false && props.validationResult?.errors?.length) {
      const count = props.validationResult.errors.length
      return `Проверка не пройдена — ${formatErrors(count)}`
    }
    return props.xmlSyncHint
  }
  if (status.value === 'warn') {
    const count = props.buildInfo.warnings.length
    if (count === 1) return 'Сборка завершена с 1 предупреждением'
    return `Сборка завершена с ${count} предупреждениями`
  }
  if (props.validationResult?.valid === true) {
    return 'XML соответствует DTD'
  }
  if (props.buildInfo) {
    return `Сгенерировано — ${formatNodes(props.buildInfo.node_count)}, без предупреждений`
  }
  return ''
})
</script>

<style scoped>
.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.results-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid transparent;
}

.results-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.results-status--ok {
  color: var(--success);
  background: color-mix(in srgb, var(--success) 10%, transparent);
  border-color: color-mix(in srgb, var(--success) 35%, var(--border));
}

.results-status--ok .results-status-dot {
  background: var(--success);
}

.results-status--warn {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 10%, transparent);
  border-color: color-mix(in srgb, var(--warning) 35%, var(--border));
}

.results-status--warn .results-status-dot {
  background: var(--warning);
}

.results-status--error {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border-color: color-mix(in srgb, var(--danger) 35%, var(--border));
}

.results-status--error .results-status-dot {
  background: var(--danger);
}

.build-info {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
}

.build-warnings-heading {
  font-size: 12px;
  color: var(--warning);
  margin: 0;
}

.build-warnings {
  font-size: 12px;
  color: var(--warning);
  margin: 0;
  padding-left: 18px;
}

.build-warnings li {
  margin-bottom: 4px;
}

.validation-errors {
  font-size: 12px;
  color: var(--danger);
  margin: 0;
  padding-left: 18px;
}

.validation-errors li {
  margin-bottom: 4px;
}

.validation-error-link {
  display: inline;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.validation-error-link:hover {
  opacity: 0.85;
}

.error-msg {
  font-size: 12px;
  color: var(--danger);
  margin: 0;
}
</style>
