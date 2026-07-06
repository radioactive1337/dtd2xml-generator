<template>
  <div
    v-if="html"
    class="dtd-doc-block"
    :class="{ compact, collapsible: isLong, expanded }"
  >
    <div class="dtd-doc-content" v-html="html" />
    <button
      v-if="isLong"
      type="button"
      class="dtd-doc-toggle"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'Свернуть' : 'Показать полностью' }}
    </button>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { dtdDocPlainText, sanitizeDtdDocHtml } from '../utils/dtdDoc'

const props = defineProps({
  text: { type: String, default: '' },
  compact: { type: Boolean, default: false },
  collapseAt: { type: Number, default: 280 },
})

const expanded = ref(false)
const html = computed(() => sanitizeDtdDocHtml(props.text))
const isLong = computed(() => dtdDocPlainText(props.text).length > props.collapseAt)

watch(
  () => props.text,
  () => {
    expanded.value = false
  },
)
</script>

<style scoped>
.dtd-doc-block {
  padding: 8px 10px;
  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
  border-left: 3px solid var(--accent);
  border-radius: 0 var(--radius) var(--radius) 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text);
}

.dtd-doc-block.compact {
  padding: 4px 0 0;
  background: none;
  border-left: none;
  font-size: 11px;
  color: var(--text-muted);
}

.dtd-doc-content :deep(p) {
  margin: 0 0 6px;
}

.dtd-doc-content :deep(p:last-child) {
  margin-bottom: 0;
}

.dtd-doc-content :deep(ul),
.dtd-doc-content :deep(ol) {
  margin: 4px 0;
  padding-left: 18px;
}

.dtd-doc-content :deep(li) {
  margin: 2px 0;
}

.dtd-doc-content :deep(code) {
  font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.92em;
}

.dtd-doc-block.collapsible:not(.expanded) .dtd-doc-content {
  max-height: 4.5em;
  overflow: hidden;
  mask-image: linear-gradient(180deg, #000 55%, transparent);
}

.dtd-doc-toggle {
  margin-top: 6px;
  padding: 0;
  border: none;
  background: none;
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
  text-decoration: underline;
}
</style>
