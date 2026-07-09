<template>
  <div class="collab-bar">
    <template v-if="!isCollaborating">
      <button type="button" class="btn-secondary btn-tint btn-tint-collab" @click="openPopup">
        Совместное редактирование
      </button>
    </template>

    <template v-else>
      <div class="collab-active">
        <span class="collab-label">Сессия:</span>
        <code class="collab-session-id">{{ sessionId }}</code>
        <button type="button" class="btn-secondary btn-sm" @click="copySessionId">
          {{ copied ? 'Скопировано' : 'Копировать' }}
        </button>
        <div v-if="participants.length" class="collab-participants" :title="participantNames">
          <span
            v-for="person in participants"
            :key="person.username"
            class="collab-avatar"
            :style="{ background: person.color }"
          >
            {{ initials(person.username) }}
          </span>
        </div>
        <button type="button" class="btn-secondary btn-sm btn-tint-danger" @click="leaveSession">
          Покинуть сессию
        </button>
      </div>
    </template>

    <div v-if="showPopup" class="collab-popup-backdrop" @click.self="closePopup">
      <div class="collab-popup card">
        <h4 class="collab-popup-title">Совместное редактирование</h4>
        <p class="collab-popup-hint">
          Создайте сессию и отправьте ID коллеге, либо введите ID существующей сессии.
        </p>
        <button type="button" class="btn-primary" @click="handleCreate">
          Создать сессию
        </button>
        <label class="collab-join-label">
          Войти по ID сессии
          <input
            v-model="joinId"
            type="text"
            class="collab-join-input"
            placeholder="UUID сессии"
            @keydown.enter.prevent="handleJoin"
          />
        </label>
        <div class="collab-popup-actions">
          <button type="button" class="btn-secondary btn-sm" @click="closePopup">Отмена</button>
          <button type="button" class="btn-primary btn-sm" :disabled="!joinId.trim()" @click="handleJoin">
            Войти
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useCollaboration } from '../composables/useCollaboration'

const props = defineProps({
  currentXml: { type: String, default: '' },
})

const {
  sessionId,
  participants,
  isCollaborating,
  createSession,
  joinSession,
  leaveSession,
} = useCollaboration()

const showPopup = ref(false)
const joinId = ref('')
const copied = ref(false)

const participantNames = computed(() =>
  participants.value.map((p) => p.username).join(', '),
)

function initials(name) {
  const parts = (name || '?').trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0] || ''}${parts[1][0] || ''}`.toUpperCase()
}

function openPopup() {
  joinId.value = ''
  showPopup.value = true
}

function closePopup() {
  showPopup.value = false
}

function handleCreate() {
  createSession(props.currentXml || '')
  closePopup()
}

function handleJoin() {
  const id = joinId.value.trim()
  if (!id) return
  joinSession(id)
  closePopup()
}

async function copySessionId() {
  if (!sessionId.value) return
  try {
    await navigator.clipboard.writeText(sessionId.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    // ignore clipboard errors
  }
}
</script>

<style scoped>
.collab-bar {
  flex-shrink: 0;
  margin-bottom: 8px;
}

.collab-active {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.collab-label {
  font-size: 12px;
  color: var(--text-muted);
}

.collab-session-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--surface2);
  border: 1px solid var(--border);
}

.collab-participants {
  display: flex;
  align-items: center;
  gap: 4px;
}

.collab-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  border: 2px solid var(--surface);
}

.btn-tint-collab {
  background: color-mix(in srgb, #8b5cf6 14%, var(--surface2));
  border-color: color-mix(in srgb, #8b5cf6 36%, var(--border));
}

.btn-tint-collab:hover:not(:disabled) {
  background: color-mix(in srgb, #8b5cf6 22%, var(--surface2));
  border-color: color-mix(in srgb, #8b5cf6 46%, var(--border));
}

.collab-popup-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--bg, #000) 40%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.collab-popup {
  width: min(380px, 92vw);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.collab-popup-title {
  margin: 0;
  font-size: 14px;
}

.collab-popup-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.collab-join-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.collab-join-input {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
}

.collab-popup-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 11px;
}
</style>
