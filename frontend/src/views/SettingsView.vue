<template>
  <div class="settings">
    <div class="card">
      <div class="panel-title">Алиасы подключений</div>
      <p class="hint">
        Алиасы БД и LLM общие — их задаёт администратор. Git-токен остаётся личным.
        Секреты хранятся только на сервере и не отображаются в интерфейсе.
      </p>

      <div v-if="loading" class="loading">Загрузка…</div>

      <template v-else>
        <section class="alias-section">
          <div class="section-header">
            <h3>Алиасы БД</h3>
          </div>
          <ul v-if="connections.databases?.length" class="alias-list">
            <li v-for="db in connections.databases" :key="db.alias" class="alias-item">
              <span class="alias-icon">DB</span>
              <div class="alias-info">
                <span class="alias-name">{{ db.alias }}</span>
                <span class="alias-meta">{{ db.driver }} · {{ db.host }}:{{ db.port }}</span>
              </div>
              <button class="btn-secondary btn-test" :disabled="isDbTesting(db.alias)" @click="testDb(db.alias)">
                {{ isDbTesting(db.alias) ? 'Проверка…' : 'Проверить' }}
              </button>
              <span
                v-if="dbStatus(db.alias) && !isDbTesting(db.alias)"
                class="status-badge"
                :class="dbStatus(db.alias).ok ? 'ok' : 'error'"
              >
                {{ dbStatus(db.alias).ok ? 'OK' : 'Ошибка' }}
              </span>
              <p
                v-if="dbStatus(db.alias) && !dbStatus(db.alias).ok && dbStatus(db.alias).message"
                class="status-detail error-msg"
              >
                {{ dbStatus(db.alias).message }}
              </p>
            </li>
          </ul>
          <div v-else class="settings-empty">
            <span class="alias-icon">DB</span>
            <p class="settings-empty-text">Общие алиасы БД не заданы</p>
            <router-link v-if="isAdmin" to="/admin" class="btn-primary">Задать в админке</router-link>
            <p v-else class="settings-empty-hint">Их задаёт администратор</p>
          </div>
        </section>

        <section class="alias-section">
          <div class="section-header">
            <h3>Алиасы LLM</h3>
          </div>
          <div v-if="connections.llm?.length > 1" class="default-llm-field">
            <label for="default-llm-select">LLM по умолчанию</label>
            <select id="default-llm-select" v-model="defaultLlmAlias" :disabled="savingDefaultLlm" @change="saveDefaultLlm">
              <option v-for="llm in connections.llm" :key="llm.alias" :value="llm.alias">{{ llm.alias }}</option>
            </select>
          </div>
          <ul v-if="connections.llm?.length" class="alias-list">
            <li v-for="llm in connections.llm" :key="llm.alias" class="alias-item">
              <span class="alias-icon llm">LLM</span>
              <div class="alias-info">
                <span class="alias-name">{{ llm.alias }}</span>
                <span class="alias-meta">{{ llm.model }} · {{ llm.base_url }}</span>
              </div>
              <button class="btn-secondary btn-test" :disabled="isLlmTesting(llm.alias)" @click="testLlm(llm.alias)">
                {{ isLlmTesting(llm.alias) ? 'Проверка…' : 'Проверить' }}
              </button>
              <span
                v-if="llmStatus(llm.alias) && !isLlmTesting(llm.alias)"
                class="status-badge"
                :class="llmStatus(llm.alias).ok ? 'ok' : 'error'"
              >
                {{ llmStatus(llm.alias).ok ? 'OK' : 'Ошибка' }}
              </span>
              <p
                v-if="llmStatus(llm.alias) && !llmStatus(llm.alias).ok && llmStatus(llm.alias).message"
                class="status-detail error-msg"
              >
                {{ llmStatus(llm.alias).message }}
              </p>
            </li>
          </ul>
          <div v-else class="settings-empty">
            <span class="alias-icon llm">LLM</span>
            <p class="settings-empty-text">Общие алиасы LLM не заданы</p>
            <router-link v-if="isAdmin" to="/admin" class="btn-primary">Задать в админке</router-link>
            <p v-else class="settings-empty-hint">Их задаёт администратор</p>
          </div>
        </section>

        <section class="alias-section">
          <div class="section-header">
            <h3>Git (эталонная библиотека)</h3>
          </div>
          <p class="hint section-hint">
            Токен для pull и push в репозиторий эталонов.
            <button type="button" class="hint-more" @click="gitHintOpen = !gitHintOpen">
              {{ gitHintOpen ? 'Скрыть' : 'Подробнее' }}
            </button>
          </p>
          <p v-if="gitHintOpen" class="hint section-hint-detail">
            Для привязки коммитов к аккаунту GitLab укажите email, совпадающий с профилем
            (или он подтянется автоматически при сохранении токена).
          </p>
          <div v-if="gitSettings.configured" class="git-settings-card">
            <div class="git-settings-row">
              <span class="alias-icon git">GIT</span>
              <div class="alias-info">
                <span class="alias-name">Доступ к репозиторию</span>
                <span class="alias-meta">
                  Токен сохранён · пользователь: {{ gitSettings.user || 'oauth2' }}
                </span>
                <span v-if="gitSettings.author_configured" class="alias-meta">
                  Автор коммитов: {{ gitSettings.author_name }} &lt;{{ gitSettings.author_email }}&gt;
                </span>
                <span v-else class="alias-meta">
                  Автор коммитов не задан — будет подтянут из GitLab при первом push
                </span>
              </div>
              <button class="btn-secondary btn-test" :disabled="gitTesting" @click="testGit">
                {{ gitTesting ? 'Проверка…' : 'Проверить' }}
              </button>
              <button class="btn-secondary btn-test" @click="openGitForm">Изменить</button>
              <button class="btn-secondary btn-test danger" @click="removeGitSettings">Удалить</button>
              <span
                v-if="gitTestStatus && !gitTesting"
                class="status-badge"
                :class="gitTestStatus.ok ? 'ok' : 'error'"
              >
                {{ gitTestStatus.ok ? 'OK' : 'Ошибка' }}
              </span>
              <p
                v-if="gitTestStatus && !gitTestStatus.ok && gitTestStatus.message"
                class="status-detail error-msg"
              >
                {{ gitTestStatus.message }}
              </p>
            </div>
          </div>
          <div v-else class="settings-empty">
            <span class="alias-icon git">GIT</span>
            <p class="settings-empty-text">Токен не задан</p>
            <button type="button" class="btn-primary" @click="openGitForm">Добавить</button>
          </div>
        </section>
      </template>

      <p v-if="error" class="error-msg">{{ error }}</p>
    </div>

    <div v-if="gitFormOpen" class="modal-overlay" @click.self="closeGitForm">
      <div class="card modal">
        <div class="panel-title">{{ gitSettings.configured ? 'Изменить Git-токен' : 'Git-токен' }}</div>
        <form @submit.prevent="saveGitForm">
          <label>Git user (для HTTPS)</label>
          <input v-model="gitForm.user" placeholder="oauth2" />
          <label>
            Token{{ gitSettings.configured ? ' (оставьте пустым, чтобы не менять)' : '' }}
          </label>
          <p class="hint inner-hint">
            <a :href="GITLAB_PAT_URL" target="_blank" rel="noopener noreferrer">Создать токен</a>
            — нажмите Create token, вставьте сюда.
          </p>
          <input v-model="gitForm.token" type="password" autocomplete="off" />
          <label>Имя в коммитах</label>
          <input v-model="gitForm.author_name" placeholder="Как в GitLab" />
          <label>Email в коммитах</label>
          <input
            v-model="gitForm.author_email"
            type="email"
            placeholder="Должен совпадать с email в GitLab"
          />
          <p class="hint inner-hint">
            GitLab привязывает коммит к аккаунту по email автора, а не по токену push.
            Email должен совпадать с профилем; пустые имя/email подтянутся из GitLab при сохранении токена.
          </p>
          <p v-if="gitFormError" class="error-msg">{{ gitFormError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="closeGitForm">Отмена</button>
            <button type="submit" class="btn-primary" :disabled="savingGitForm">Сохранить</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  getConnections,
  setDefaultLlmAlias,
  testDbConnection,
  testLlmConnection,
  getGitSettings,
  updateGitSettings,
  deleteGitSettings,
  testGitConnection,
} from '../api/config'
import { useAuth } from '../composables/useAuth'

const { isAdmin } = useAuth()

const GITLAB_PAT_URL =
  'https://<ВАШ_GITLAB_ХОСТ>/-/user_settings/personal_access_tokens?name=xml-generator&scopes=api&description=Token+for+XML+generator'

const connections = ref({ databases: [], llm: [], default_llm: null })
const defaultLlmAlias = ref('')
const savingDefaultLlm = ref(false)
const loading = ref(true)
const error = ref('')
const dbTests = ref({})
const llmTests = ref({})
const gitSettings = ref({ configured: false, user: 'oauth2' })
const gitTestStatus = ref(null)
const gitTesting = ref(false)
const gitFormOpen = ref(false)
const gitHintOpen = ref(false)
const savingGitForm = ref(false)
const gitFormError = ref('')
const gitForm = ref({ token: '', user: 'oauth2', author_name: '', author_email: '' })

function dbStatus(alias) {
  return dbTests.value[alias] ?? null
}

function llmStatus(alias) {
  return llmTests.value[alias] ?? null
}

function isDbTesting(alias) {
  return dbTests.value[alias]?.testing === true
}

function isLlmTesting(alias) {
  return llmTests.value[alias]?.testing === true
}

async function loadConnections() {
  connections.value = await getConnections()
  defaultLlmAlias.value = connections.value.default_llm || connections.value.llm?.[0]?.alias || ''
  gitSettings.value = await getGitSettings()
}

function openGitForm() {
  gitFormError.value = ''
  gitForm.value = {
    token: '',
    user: gitSettings.value.user || 'oauth2',
    author_name: gitSettings.value.author_name || '',
    author_email: gitSettings.value.author_email || '',
  }
  gitFormOpen.value = true
}

function closeGitForm() {
  gitFormOpen.value = false
  gitFormError.value = ''
}

async function saveGitForm() {
  gitFormError.value = ''
  if (!gitSettings.value.configured && !gitForm.value.token.trim()) {
    gitFormError.value = 'Укажите токен'
    return
  }
  savingGitForm.value = true
  error.value = ''
  try {
    const payload = { user: gitForm.value.user.trim() || 'oauth2' }
    if (gitForm.value.token.trim()) {
      payload.token = gitForm.value.token.trim()
    } else if (!gitSettings.value.configured) {
      gitFormError.value = 'Укажите токен'
      return
    }
    if (gitForm.value.author_name.trim()) {
      payload.author_name = gitForm.value.author_name.trim()
    }
    if (gitForm.value.author_email.trim()) {
      payload.author_email = gitForm.value.author_email.trim()
    }
    gitSettings.value = await updateGitSettings(payload)
    gitTestStatus.value = null
    closeGitForm()
  } catch (e) {
    gitFormError.value = e.message
  } finally {
    savingGitForm.value = false
  }
}

async function removeGitSettings() {
  if (!confirm('Удалить сохранённый Git-токен?')) return
  error.value = ''
  try {
    await deleteGitSettings()
    gitSettings.value = { configured: false, user: 'oauth2' }
    gitTestStatus.value = null
  } catch (e) {
    error.value = e.message
  }
}

async function testGit() {
  gitTesting.value = true
  gitTestStatus.value = null
  try {
    const result = await testGitConnection()
    gitTestStatus.value = { ok: result.ok, message: result.message }
  } catch (e) {
    gitTestStatus.value = { ok: false, message: e.message }
  } finally {
    gitTesting.value = false
  }
}

async function testDb(alias) {
  dbTests.value = { ...dbTests.value, [alias]: { testing: true } }
  try {
    const result = await testDbConnection(alias)
    dbTests.value = { ...dbTests.value, [alias]: { ok: result.ok, message: result.message } }
  } catch (e) {
    dbTests.value = { ...dbTests.value, [alias]: { ok: false, message: e.message } }
  }
}

async function testLlm(alias) {
  llmTests.value = { ...llmTests.value, [alias]: { testing: true } }
  try {
    const result = await testLlmConnection(alias)
    llmTests.value = { ...llmTests.value, [alias]: { ok: result.ok, message: result.message } }
  } catch (e) {
    llmTests.value = { ...llmTests.value, [alias]: { ok: false, message: e.message } }
  }
}

async function saveDefaultLlm() {
  if (!defaultLlmAlias.value) return
  const previous = connections.value.default_llm || ''
  savingDefaultLlm.value = true
  error.value = ''
  try {
    const result = await setDefaultLlmAlias(defaultLlmAlias.value)
    connections.value.default_llm = result.default_llm
    defaultLlmAlias.value = result.default_llm
  } catch (e) {
    error.value = e.message
    defaultLlmAlias.value = previous
  } finally {
    savingDefaultLlm.value = false
  }
}

onMounted(async () => {
  try {
    await loadConnections()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.settings {
  max-width: 920px;
  width: 100%;
  margin: 0 auto;
}

.hint {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 20px;
  line-height: 1.5;
}

.inner-hint {
  margin-bottom: 0;
}

code {
  background: var(--surface2);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.alias-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.alias-section h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--text-muted);
}

.default-llm-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.default-llm-field label {
  font-size: 13px;
  font-weight: 500;
}

.alias-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alias-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--surface2);
  border-radius: var(--radius);
  font-size: 14px;
}

.alias-info {
  flex: 1;
  min-width: 120px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.alias-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.alias-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.btn-test {
  padding: 4px 10px;
  font-size: 12px;
}

.btn-test.danger {
  color: var(--danger);
}

.status-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
}

.status-badge.ok {
  background: color-mix(in srgb, var(--success) 15%, transparent);
  color: var(--success);
}

.status-badge.error {
  background: color-mix(in srgb, var(--danger) 15%, transparent);
  color: var(--danger);
}

.status-detail {
  width: 100%;
  margin: 0;
  font-size: 12px;
}

.alias-icon {
  background: var(--accent);
  color: white;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
}

.alias-icon.llm {
  background: var(--llm-accent);
}

.alias-icon.git {
  background: #6b7280;
}

.section-hint {
  margin-top: 0;
  margin-bottom: 12px;
}

.section-hint-detail {
  margin-top: -4px;
  margin-bottom: 12px;
}

.hint-more {
  display: inline;
  margin-left: 4px;
  padding: 0;
  border: none;
  background: none;
  color: var(--accent);
  font: inherit;
  font-size: inherit;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.hint-more:hover {
  opacity: 0.85;
}

.git-settings-card {
  background: var(--surface2);
  border-radius: var(--radius);
  padding: 10px 12px;
}

.git-settings-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.settings-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 20px 12px;
  background: var(--surface2);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  text-align: center;
}

.settings-empty-text {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.settings-empty-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.settings-empty :deep(.btn-primary) {
  text-decoration: none;
}

.loading {
  color: var(--text-muted);
  font-size: 14px;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}

.modal {
  width: 100%;
  max-width: 440px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal label {
  display: block;
  font-size: 13px;
  margin-top: 10px;
  margin-bottom: 4px;
}

.modal input,
.modal select {
  width: 100%;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
