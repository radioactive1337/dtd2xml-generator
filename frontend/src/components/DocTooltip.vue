<template>
  <span
    ref="anchorRef"
    class="doc-tooltip-anchor"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
    @focusin="onEnter"
    @focusout="onLeave"
  >
    <slot />
    <Teleport to="body">
      <div
        v-if="visible && plainText"
        ref="panelRef"
        class="doc-tooltip-panel"
        role="tooltip"
        :style="panelStyle"
      >
        {{ plainText }}
      </div>
    </Teleport>
  </span>
</template>

<script setup>
import { ref, onBeforeUnmount, computed } from 'vue'
import { dtdDocPlainText } from '../utils/dtdDoc'

const props = defineProps({
  text: { type: String, default: '' },
})

const plainText = computed(() => dtdDocPlainText(props.text))

const anchorRef = ref(null)
const panelRef = ref(null)
const visible = ref(false)
const panelStyle = ref({})
let showTimer = null
let hideTimer = null

function clearTimers() {
  if (showTimer) {
    clearTimeout(showTimer)
    showTimer = null
  }
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

function updatePosition() {
  const anchor = anchorRef.value
  if (!anchor) return
  const rect = anchor.getBoundingClientRect()
  const gap = 6
  const maxWidth = Math.min(360, window.innerWidth - 16)
  let left = rect.left
  if (left + maxWidth > window.innerWidth - 8) {
    left = window.innerWidth - maxWidth - 8
  }
  left = Math.max(8, left)

  let top = rect.bottom + gap
  const panel = panelRef.value
  const panelHeight = panel?.offsetHeight || 120
  if (top + panelHeight > window.innerHeight - 8) {
    top = Math.max(8, rect.top - panelHeight - gap)
  }

  panelStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    maxWidth: `${maxWidth}px`,
  }
}

function showPanel() {
  if (!plainText.value?.trim()) return
  visible.value = true
  requestAnimationFrame(updatePosition)
}

function onEnter() {
  clearTimers()
  hideTimer = null
  showTimer = setTimeout(showPanel, 350)
}

function onLeave() {
  clearTimers()
  showTimer = null
  hideTimer = setTimeout(() => {
    visible.value = false
  }, 100)
}

onBeforeUnmount(clearTimers)
</script>

<style scoped>
.doc-tooltip-anchor {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
}

.doc-tooltip-panel {
  position: fixed;
  z-index: 300;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 16px color-mix(in srgb, var(--text) 15%, transparent);
  white-space: pre-wrap;
  word-break: break-word;
  pointer-events: none;
}
</style>
