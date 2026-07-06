<template>
  <div class="element-picker" ref="rootRef">
    <input
      ref="inputRef"
      type="text"
      :value="modelValue"
      :placeholder="placeholder"
      class="picker-input"
      :class="{ invalid }"
      autocomplete="off"
      role="combobox"
      :aria-expanded="isOpen"
      aria-autocomplete="list"
      @input="onInput"
      @focus="openDropdown"
      @blur="onBlur"
      @keydown="onKeydown"
    />
    <p v-if="error" class="picker-error">{{ error }}</p>
    <DtdDocBlock
      v-else-if="showSelectedDoc && selectedDoc"
      :text="selectedDoc"
      compact
    />
    <Teleport to="body">
      <div
        v-if="isOpen"
        ref="dropdownRef"
        class="picker-dropdown"
        role="listbox"
        :style="dropdownStyle"
        @mousedown.prevent="clearCloseTimer"
      >
        <p v-if="!displayed.matches.length" class="picker-empty">ничего не найдено</p>
        <ul v-else class="picker-list">
          <li
            v-for="(el, i) in displayed.matches"
            :key="el"
            class="picker-option"
            :class="{ highlighted: i === highlightedIndex }"
            role="option"
            :aria-selected="i === highlightedIndex"
            @mousedown.prevent="selectElement(el)"
          >
            <span class="picker-option-name">{{ el }}</span>
            <span v-if="docPreview(el)" class="picker-option-doc">{{ docPreview(el) }}</span>
          </li>
        </ul>
        <p class="picker-counter">{{ displayed.matches.length }} из {{ displayed.total }}</p>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { filterElements, resolveElementName } from '../utils/elementFilter'
import { dtdDocPreview } from '../utils/dtdDoc'
import DtdDocBlock from './DtdDocBlock.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  elements: { type: Array, default: () => [] },
  elementDocs: { type: Object, default: () => ({}) },
  showSelectedDoc: { type: Boolean, default: true },
  placeholder: { type: String, default: '' },
  invalid: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const rootRef = ref(null)
const inputRef = ref(null)
const dropdownRef = ref(null)
const isOpen = ref(false)
const highlightedIndex = ref(-1)
const dropdownStyle = ref({})
let closeTimer = null

const displayed = computed(() => filterElements(props.elements, props.modelValue))

const selectedDoc = computed(() => {
  const resolved = resolveElementName(props.modelValue, props.elements)
  return resolved ? docFor(resolved) : ''
})

function docFor(name) {
  return props.elementDocs[name] || ''
}

function docPreview(name) {
  const doc = docFor(name)
  return doc ? dtdDocPreview(doc) : ''
}

watch(
  () => props.modelValue,
  () => {
    highlightedIndex.value = -1
  },
)

onClickOutside(rootRef, closeDropdown, { ignore: [dropdownRef] })

function clearCloseTimer() {
  if (closeTimer) {
    clearTimeout(closeTimer)
    closeTimer = null
  }
}

function closeDropdown() {
  clearCloseTimer()
  isOpen.value = false
  highlightedIndex.value = -1
  removePositionListeners()
}

function updateDropdownPosition() {
  const input = inputRef.value
  if (!input) return
  const rect = input.getBoundingClientRect()
  dropdownStyle.value = {
    top: `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
    width: `${rect.width}px`,
  }
}

function onPositionChange() {
  if (isOpen.value) updateDropdownPosition()
}

function addPositionListeners() {
  window.addEventListener('scroll', onPositionChange, true)
  window.addEventListener('resize', onPositionChange)
}

function removePositionListeners() {
  window.removeEventListener('scroll', onPositionChange, true)
  window.removeEventListener('resize', onPositionChange)
}

watch(isOpen, async (open) => {
  if (open) {
    await nextTick()
    updateDropdownPosition()
    addPositionListeners()
  } else {
    removePositionListeners()
  }
})

onBeforeUnmount(() => {
  clearCloseTimer()
  removePositionListeners()
})

function openDropdown() {
  clearCloseTimer()
  isOpen.value = true
}

function scheduleClose() {
  clearCloseTimer()
  closeTimer = setTimeout(() => {
    closeDropdown()
  }, 150)
}

function onBlur() {
  scheduleClose()
}

function onInput(event) {
  const value = event.target.value
  emit('update:modelValue', value)
  clearCloseTimer()
  isOpen.value = true
  highlightedIndex.value = -1
  nextTick(updateDropdownPosition)
}

function confirmSelection(value) {
  clearCloseTimer()
  const resolved = resolveElementName(value, props.elements)
  emit('update:modelValue', resolved)
  emit('confirm', resolved)
  closeDropdown()
}

function selectElement(el) {
  confirmSelection(el)
}

function onKeydown(event) {
  if (!isOpen.value && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
    isOpen.value = true
    event.preventDefault()
    return
  }

  if (event.key === 'Escape') {
    closeDropdown()
    event.preventDefault()
    return
  }

  if (event.key === 'Enter') {
    event.preventDefault()
    const count = displayed.value.matches.length
    if (isOpen.value && highlightedIndex.value >= 0 && highlightedIndex.value < count) {
      confirmSelection(displayed.value.matches[highlightedIndex.value])
    } else {
      confirmSelection(props.modelValue)
    }
    inputRef.value?.blur()
    return
  }

  const count = displayed.value.matches.length
  if (!count) return

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlightedIndex.value = highlightedIndex.value < count - 1 ? highlightedIndex.value + 1 : 0
    return
  }

  if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlightedIndex.value = highlightedIndex.value > 0 ? highlightedIndex.value - 1 : count - 1
  }
}
</script>

<style scoped>
.element-picker {
  position: relative;
  width: 100%;
}

.picker-input {
  width: 100%;
}

.picker-input.invalid {
  border-color: var(--danger);
}

.picker-input.invalid:focus {
  border-color: var(--danger);
}

.picker-error {
  font-size: 11px;
  color: var(--danger);
  margin: 4px 0 0;
}

.picker-dropdown {
  position: fixed;
  z-index: 200;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 16px color-mix(in srgb, var(--text) 15%, transparent);
  max-height: 240px;
  display: flex;
  flex-direction: column;
}

.picker-list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.picker-option {
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.picker-option-name {
  font-size: 13px;
}

.picker-option-doc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.picker-option.highlighted,
.picker-option:hover {
  background: var(--surface2);
}

.picker-empty {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
  padding: 8px 12px;
}

.picker-counter {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
  padding: 4px 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
</style>
