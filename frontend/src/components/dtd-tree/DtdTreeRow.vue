<template>
  <div
    class="tree-row"
    :class="{ 'search-highlight': highlightedPath === item.path }"
  >
    <span class="indent" :style="{ width: `${item.depth * 20}px` }" />
    <button v-if="item.hasChildren" class="expand-btn" @click="$emit('toggle-expand', item)">
      {{ item.expanded ? '▼' : '▶' }}
    </button>
    <span v-else class="expand-spacer" />
    <button
      type="button"
      class="tree-checkbox"
      :class="{ checked: item.checked, disabled: item.locked }"
      :disabled="item.locked"
      :aria-checked="item.checked"
      role="checkbox"
      @click="$emit('toggle-check', item.path)"
    />
    <span
      class="node-name"
      :class="{ required: item.required, 'group-expr': item.isGroupLabel }"
      :title="item.displayName"
    >{{ item.displayName }}</span>
    <span v-if="item.quantifier" class="quantifier">{{ item.quantifier }}</span>
  </div>
</template>

<script setup>
defineProps({
  item: { type: Object, required: true },
  highlightedPath: { type: String, default: null },
})

defineEmits(['toggle-expand', 'toggle-check'])
</script>

<style scoped>
.tree-row {
  display: flex;
  align-items: center;
  gap: 0;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  height: 32px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
  padding-left: 8px;
  overflow: hidden;
}

.tree-row.search-highlight {
  background: color-mix(in srgb, var(--accent) 28%, transparent);
  animation: search-highlight-fade 2s ease-out;
}

@keyframes search-highlight-fade {
  0% { background: color-mix(in srgb, var(--accent) 40%, transparent); }
  100% { background: color-mix(in srgb, var(--accent) 28%, transparent); }
}

.indent {
  flex-shrink: 0;
  display: inline-block;
}

.expand-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  padding: 0;
  width: 20px;
  min-width: 20px;
  height: 20px;
  font-size: 10px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.expand-spacer {
  flex-shrink: 0;
  display: inline-block;
  width: 20px;
  min-width: 20px;
}

.tree-checkbox {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  min-width: 16px;
  margin: 0 6px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--bg);
  cursor: pointer;
  position: relative;
}

.tree-checkbox.checked {
  background: var(--accent);
  border-color: var(--accent);
}

.tree-checkbox.checked::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 1px;
  width: 5px;
  height: 9px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

.tree-checkbox.disabled {
  opacity: 0.55;
  cursor: default;
}

.node-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 4px;
}

.node-name.required { font-weight: 600; }

.node-name.group-expr {
  font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  color: var(--text-muted);
}

.quantifier {
  color: var(--accent);
  font-size: 12px;
  font-family: monospace;
  flex-shrink: 0;
  margin-right: 12px;
}
</style>
