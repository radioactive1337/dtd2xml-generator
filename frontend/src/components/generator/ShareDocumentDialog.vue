<template>
  <div v-if="open" class="share-dialog-backdrop" @click.self="close">
    <form class="share-dialog" @submit.prevent="submit">
      <h4 class="share-dialog-title">Поделиться XML</h4>

      <p v-if="documentLabel" class="share-document-label">
        Документ: <strong>{{ documentLabel }}</strong>
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
        <input
          v-model="recipientUsername"
          type="text"
          class="share-input"
          autocomplete="username"
          placeholder="ivan"
          required
          autofocus
          :disabled="submitting"
          @input="onRecipientInput"
        />
      </label>

      <p v-if="recipientChecking" class="share-hint">Проверка пользователя…</p>
      <p v-else-if="recipientUsername.trim() && recipientExists === true" class="share-ok">
        Пользователь найден
      </p>
      <p v-else-if="recipientUsername.trim() && recipientExists === false" class="share-error-inline">
        Пользователь не найден
      </p>
      <p v-if="suggestions.length" class="share-suggestions">
        Возможно:
        <button
          v-for="name in suggestions"
          :key="name"
          type="button"
          class="link-btn"
          @click="pickSuggestion(name)"
        >
          {{ name }}
        </button>
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
import { checkUsernameExists } from '../../api/auth'

const props = defineProps({
  open: { type: Boolean, default: false },
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
const suggestions = ref([])

let recipientTimer = null

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
  suggestions.value = []
}

function close() {
  if (props.submitting) return
  emit('close')
}

function pickSuggestion(name) {
  recipientUsername.value = name
  suggestions.value = []
  scheduleRecipientCheck()
}

function onRecipientInput() {
  recipientExists.value = null
  suggestions.value = []
  scheduleRecipientCheck()
}

function scheduleRecipientCheck() {
  if (recipientTimer) clearTimeout(recipientTimer)
  const value = recipientUsername.value.trim()
  if (!value) {
    recipientExists.value = null
    recipientChecking.value = false
    return
  }
  recipientChecking.value = true
  recipientTimer = setTimeout(() => {
    verifyRecipient(value)
  }, 350)
}

async function verifyRecipient(username) {
  if (username !== recipientUsername.value.trim()) return
  recipientChecking.value = true
  try {
    const result = await checkUsernameExists(username)
    if (username !== recipientUsername.value.trim()) return
    recipientExists.value = result.exists
    suggestions.value = result.exists ? [] : (result.suggestions || [])
  } catch (err) {
    if (username !== recipientUsername.value.trim()) return
    recipientExists.value = null
  } finally {
    if (username === recipientUsername.value.trim()) {
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
    } else if (recipientTimer) {
      clearTimeout(recipientTimer)
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

.share-input {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
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

.share-suggestions {
  margin: -4px 0 8px;
  font-size: 11px;
  color: var(--text-muted);
}

.link-btn {
  margin-left: 6px;
  padding: 0;
  border: none;
  background: none;
  color: var(--accent);
  cursor: pointer;
  font-size: inherit;
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
