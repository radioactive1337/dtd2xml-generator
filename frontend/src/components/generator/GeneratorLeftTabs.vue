<template>
  <nav
    class="left-tabs-bar"
    role="tablist"
    aria-label="Панели генерации"
  >
    <button
      v-for="tab in tabs"
      :id="`left-tab-${tab.id}`"
      :key="tab.id"
      type="button"
      role="tab"
      class="left-tab-btn"
      :class="{ active: activeTab === tab.id }"
      :aria-selected="activeTab === tab.id"
      :tabindex="activeTab === tab.id ? 0 : -1"
      @click="$emit('update:activeTab', tab.id)"
      @keydown="$emit('tab-keydown', $event, tab.id)"
    >
      {{ tab.label }}
      <span
        v-if="tab.id === 'data' && showDataBadge"
        class="left-tab-badge left-tab-badge--warn"
        aria-label="Требует внимания"
      />
      <span
        v-if="tab.id === 'results' && resultsTabBadge"
        class="left-tab-badge"
        :class="`left-tab-badge--${resultsTabBadge}`"
        :aria-label="resultsTabBadgeLabel"
      />
    </button>
  </nav>
</template>

<script setup>
defineProps({
  tabs: { type: Array, required: true },
  activeTab: { type: String, required: true },
  showDataBadge: { type: Boolean, default: false },
  resultsTabBadge: { type: String, default: null },
  resultsTabBadgeLabel: { type: String, default: '' },
})

defineEmits(['update:activeTab', 'tab-keydown'])
</script>

<style scoped>
.left-tabs-bar {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  padding: 8px 12px 0;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}

.left-tab-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  background: none;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.left-tab-btn:hover {
  color: var(--text);
}

.left-tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.left-tab-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 4px 4px 0 0;
}

.left-tab-badge {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.left-tab-badge--warn {
  background: var(--warning);
}

.left-tab-badge--error {
  background: var(--danger);
}

.left-tab-badge--ok {
  background: var(--success);
}
</style>
