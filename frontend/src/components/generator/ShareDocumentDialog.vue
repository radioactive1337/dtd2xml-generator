<template>
  <div v-if="open" class="share-dialog-backdrop" @click.self="close">
    <form class="share-dialog" @submit.prevent="submit">
      <h4 class="share-dialog-title">{{ dialogTitle }}</h4>

      <p v-if="documentLabel" class="share-document-label">
        {{ itemLabelPrefix }}: <strong>{{ documentLabel }}</strong>
      </p>

      <label v-if="requireDocumentName" class="share-label">
        Имя документа у получателя
        <input
          v-model="documentName"
          type="text"
          class="share-input"
          required
          :disabled="submitting"
        />
      </label>

      <label class="share-label">
        Имя получателя
        <div class="recipient-field">
          <input
            v-model="recipientUsername"
            type="text"
            class="share-input"
            autocomplete="off"
            placeholder="ivan"
            required
            autofocus
            role="combobox"
            :aria-expanded="showDropdown"
            aria-autocomplete="list"
            :disabled="submitting"
            @input="onRecipientInput"
            @focus="onRecipientFocus"
            @blur="onRecipientBlur"
            @keydown="onRecipientKeydown"
          />
          <ul
            v-if="showDropdown"
            class="recipient-dropdown"
            role="listbox"
            @mousedown.prevent
          >
            <li
              v-for="(name, index) in userMatches"
              :key="name"
              class="recipient-option"
              :class="{ highlighted: index === highlightedIndex }"
              role="option"
              :aria-selected="index === highlightedIndex"
              @mousedown.prevent="pickSuggestion(name)"
            >
              {{ name }}
            </li>
          </ul>
        </div>
      </label>

      <p v-if="recipientChecking" class="share-hint">Поиск пользователей…</p>
      <p v-else-if="recipientUsername.trim() && recipientExists === true" class="share-ok">
        Пользователь найден
      </p>
      <p
        v-else-if="recipientUsername.trim() && recipientExists === false && !userMatches.length"
        class="share-error-inline"
      >
        Пользователь не найден
      </p>
      <p
        v-else-if="recipientUsername.trim() && userMatches.length && recipientExists === false"
        class="share-hint"
      >
        Выберите пользователя из списка
      </p>

      <label class="share-label">
        Сообщение (необязательно)
        <input
          v-model="message"
          type="text"
          class="share-input"
          :disabled="submitting"
        />
      </label>

      <p v-if="errorMessage" class="share-error" role="alert">{{ errorMessage }}</p>
      <p v-if="successMessage" class="share-success">{{ successMessage }}</p>

      <div class="share-dialog-actions">
        <button type="button" class="btn-secondary btn-sm" :disabled="submitting" @click="close">
          Отмена
        </button>
        <button
          type="submit"
          class="btn-primary btn-sm"
          :disabled="!canSubmit || submitting"
        >
          {{ submitting ? 'Отправка…' : 'Отправить' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { searchUsers } from '../../api/auth'

const props = defineProps({
  open: { type: Boolean, default: false },
  dialogTitle: { type: String, default: 'Поделиться XML' },
  itemLabelPrefix: { type: String, default: 'Документ' },
  documentLabel: { type: String, default: '' },
  requireDocumentName: { type: Boolean, default: false },
  defaultDocumentName: { type: String, default: '' },
  submitting: { type: Boolean, default: false },
  errorMessage: { type: String, default: '' },
})

const emit = defineEmits(['close', 'submit'])

const recipientUsername = ref('')
const documentName = ref('')
const message = ref('')
const successMessage = ref('')
const recipientExists = ref(null)
const recipientChecking = ref(false)
const userMatches = ref([])
const dropdownOpen = ref(false)
const highlightedIndex = ref(-1)

let recipientTimer = null
let blurTimer = null

const showDropdown = computed(
  () => dropdownOpen.value && userMatches.value.length > 0 && recipientExists.value !== true,
)

const canSubmit = computed(() => {
  const recipient = recipientUsername.value.trim()
  const nameOk = !props.requireDocumentName || documentName.value.trim()
  return Boolean(recipient && nameOk && recipientExists.value === true)
})

function resetForm() {
  recipientUsername.value = ''
  documentName.value = props.defaultDocumentName || ''
  message.value = ''
  successMessage.value = ''
  recipientExists.value = null
  recipientChecking.value = false
  userMatches.value = []
  dropdownOpen.value = false
  highlightedIndex.value = -1
}

function close() {
  if (props.submitting) return
  emit('close')
}

function pickSuggestion(name) {
  recipientUsername.value = name
  userMatches.value = []
  dropdownOpen.value = false
  highlightedIndex.value = -1
  scheduleRecipientSearch()
}

function onRecipientInput() {
  recipientExists.value = null
  dropdownOpen.value = true
  highlightedIndex.value = -1
  scheduleRecipientSearch()
}

function onRecipientFocus() {
  dropdownOpen.value = true
  if (recipientUsername.value.trim()) {
    scheduleRecipientSearch()
  }
}

function onRecipientBlur() {
  blurTimer = setTimeout(() => {
    dropdownOpen.value = false
    highlightedIndex.value = -1
  }, 150)
}

function onRecipientKeydown(event) {
  if (!showDropdown.value) return

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlightedIndex.value = Math.min(
      highlightedIndex.value + 1,
      userMatches.value.length - 1,
    )
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlightedIndex.value = Math.max(highlightedIndex.value - 1, 0)
  } else if (event.key === 'Enter' && highlightedIndex.value >= 0) {
    event.preventDefault()
    pickSuggestion(userMatches.value[highlightedIndex.value])
  } else if (event.key === 'Escape') {
    dropdownOpen.value = false
    highlightedIndex.value = -1
  }
}

function scheduleRecipientSearch() {
  if (recipientTimer) clearTimeout(recipientTimer)
  const value = recipientUsername.value.trim()
  if (!value) {
    recipientExists.value = null
    userMatches.value = []
    recipientChecking.value = false
    return
  }
  recipientChecking.value = true
  recipientTimer = setTimeout(() => {
    fetchRecipientMatches(value)
  }, 250)
}

async function fetchRecipientMatches(query) {
  if (query !== recipientUsername.value.trim()) return
  recipientChecking.value = true
  try {
    const result = await searchUsers(query)
    if (query !== recipientUsername.value.trim()) return
    recipientExists.value = result.exact_match
    userMatches.value = result.matches || []
    if (result.exact_match) {
      dropdownOpen.value = false
      highlightedIndex.value = -1
    }
  } catch {
    if (query !== recipientUsername.value.trim()) return
    recipientExists.value = null
    userMatches.value = []
  } finally {
    if (query === recipientUsername.value.trim()) {
      recipientChecking.value = false
    }
  }
}

async function submit() {
  if (!canSubmit.value || props.submitting) return
  successMessage.value = ''
  emit('submit', {
    recipientUsername: recipientUsername.value.trim(),
    message: message.value.trim(),
    name: props.requireDocumentName ? documentName.value.trim() : undefined,
  })
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      resetForm()
    } else {
      if (recipientTimer) clearTimeout(recipientTimer)
      if (blurTimer) clearTimeout(blurTimer)
    }
  },
)

watch(
  () => props.defaultDocumentName,
  (value) => {
    if (props.open && props.requireDocumentName && !documentName.value) {
      documentName.value = value || ''
    }
  },
)
</script>

<style scoped>
.share-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
}

.share-dialog {
  width: min(420px, calc(100vw - 32px));
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.share-dialog-title {
  margin: 0 0 12px;
  font-size: 14px;
}

.share-document-label {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--text-muted);
}

.share-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--text-muted);
}

.recipient-field {
  position: relative;
}

.share-input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  box-sizing: border-box;
}

.recipient-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 10;
  margin: 0;
  padding: 4px 0;
  list-style: none;
  max-height: 160px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.recipient-option {
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
}

.recipient-option:hover,
.recipient-option.highlighted {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}

.share-hint {
  margin: -6px 0 8px;
  font-size: 11px;
  color: var(--text-muted);
}

.share-ok {
  margin: -6px 0 8px;
  font-size: 11px;
  color: var(--success, #2d7a3a);
}

.share-error-inline {
  margin: -6px 0 8px;
  font-size: 11px;
  color: var(--danger);
}

.share-error {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--danger);
}

.share-success {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--success, #2d7a3a);
}

.share-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
