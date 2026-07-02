<template>
  <div class="login-page">
    <div class="card login-card">
      <div class="panel-title">Вход</div>
      <p class="hint">Введите логин для доступа к своему рабочему пространству.</p>

      <form v-if="step === 'input'" @submit.prevent="handleSubmit">
        <label for="username">Логин</label>
        <input
          id="username"
          v-model="username"
          type="text"
          autocomplete="username"
          placeholder="ivan"
          :disabled="loading"
        />
        <p v-if="error" class="error-msg">{{ error }}</p>
        <button type="submit" class="btn-primary" :disabled="loading || !username.trim()">
          {{ loading ? 'Проверка…' : 'Войти' }}
        </button>
      </form>

      <div v-else class="confirm-step">
        <p class="confirm-text">
          Пользователь <strong>{{ pendingUsername }}</strong> не найден.
        </p>
        <p v-if="suggestions.length" class="suggestions">
          Возможно, вы имели в виду:
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
        <p class="confirm-hint">Создать нового пользователя или исправить логин?</p>
        <div class="confirm-actions">
          <button type="button" class="btn-secondary" @click="reset">Исправить логин</button>
          <button type="button" class="btn-primary" :disabled="loading" @click="confirmCreate">
            {{ loading ? 'Создание…' : 'Создать нового' }}
          </button>
        </div>
        <p v-if="error" class="error-msg">{{ error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const router = useRouter()
const route = useRoute()
const { login, loading } = useAuth()

const step = ref('input')
const username = ref('')
const pendingUsername = ref('')
const suggestions = ref([])
const error = ref('')

function reset() {
  step.value = 'input'
  error.value = ''
  suggestions.value = []
}

function pickSuggestion(name) {
  username.value = name
  step.value = 'input'
  suggestions.value = []
  handleSubmit()
}

async function handleSubmit() {
  error.value = ''
  const name = username.value.trim()
  if (!name) return

  try {
    await login(name, false)
    const redirect = route.query.redirect || '/'
    router.replace(redirect)
  } catch (e) {
    if (e.response?.status === 409) {
      pendingUsername.value = name
      const detail = e.response?.data?.detail
      if (detail && typeof detail === 'object') {
        suggestions.value = detail.suggestions || []
        error.value = detail.message || ''
      } else {
        suggestions.value = []
        error.value = ''
      }
      step.value = 'confirm'
      return
    }
    error.value = e.message
  }
}

async function confirmCreate() {
  error.value = ''
  try {
    await login(pendingUsername.value, true)
    const redirect = route.query.redirect || '/'
    router.replace(redirect)
  } catch (e) {
    error.value = e.message
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 48px;
}

.login-card {
  width: 100%;
  max-width: 420px;
}

.hint {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 20px;
  line-height: 1.5;
}

label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

input {
  width: 100%;
  margin-bottom: 16px;
}

.confirm-text {
  font-size: 14px;
  margin-bottom: 12px;
}

.confirm-hint {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 16px;
}

.confirm-actions {
  display: flex;
  gap: 10px;
}

.suggestions {
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.6;
}

.link-btn {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0 4px;
  font-size: 13px;
  text-decoration: underline;
}

.link-btn:hover {
  color: var(--text);
}
</style>
