<template>
  <div class="settings">
    <div class="card">
      <div class="panel-title">Алиасы подключений</div>
      <p class="hint">
        Настройте свои подключения к БД и LLM. Секреты хранятся только на сервере и не отображаются в интерфейсе.
      </p>

      <div v-if="loading" class="loading">Загрузка…</div>

      <template v-else>
        <section class="alias-section">
          <div class="section-header">
            <h3>Алиасы БД</h3>
            <button class="btn-secondary btn-small" @click="openDbForm()">+ Добавить</button>
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
              <button class="btn-secondary btn-test" @click="openDbForm(db)">Изменить</button>
              <button class="btn-secondary btn-test danger" @click="removeDb(db.alias)">Удалить</button>
              <span v-if="dbStatus(db.alias)" class="status-badge" :class="dbStatus(db.alias).ok ? 'ok' : 'error'">
                {{ dbStatus(db.alias).ok ? 'OK' : 'Ошибка' }}
              </span>
              <p v-if="dbStatus(db.alias)?.message" class="status-detail" :class="dbStatus(db.alias).ok ? 'ok-msg' : 'error-msg'">
                {{ dbStatus(db.alias).message }}
              </p>
            </li>
          </ul>
          <p v-else class="empty">Алиасы БД не настроены.</p>
        </section>

        <section class="alias-section">
          <div class="section-header">
            <h3>Алиасы LLM</h3>
            <button class="btn-secondary btn-small" @click="openLlmForm()">+ Добавить</button>
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
              <button class="btn-secondary btn-test" @click="openLlmForm(llm)">Изменить</button>
              <button class="btn-secondary btn-test danger" @click="removeLlm(llm.alias)">Удалить</button>
              <span v-if="llmStatus(llm.alias)" class="status-badge" :class="llmStatus(llm.alias).ok ? 'ok' : 'error'">
                {{ llmStatus(llm.alias).ok ? 'OK' : 'Ошибка' }}
              </span>
              <p v-if="llmStatus(llm.alias)?.message" class="status-detail" :class="llmStatus(llm.alias).ok ? 'ok-msg' : 'error-msg'">
                {{ llmStatus(llm.alias).message }}
              </p>
            </li>
          </ul>
          <p v-else class="empty">Алиасы LLM не настроены.</p>
        </section>

        <section class="setup-hint card inner">
          <div class="panel-title">Серверные настройки</div>
          <p class="hint inner-hint">
            Глобальные параметры Oracle (<code>oracle_client_lib_dir</code> и др.) настраиваются администратором в
            <code>config/app.json</code> на сервере.
          </p>
        </section>
      </template>

      <p v-if="error" class="error-msg">{{ error }}</p>
    </div>

    <div v-if="dbFormOpen" class="modal-overlay" @click.self="closeDbForm">
      <div class="card modal">
        <div class="panel-title">{{ dbForm.alias && dbFormEditing ? 'Изменить БД' : 'Новый алиас БД' }}</div>
        <form @submit.prevent="saveDbForm">
          <label>Алиас</label>
          <input v-model="dbForm.alias" :disabled="dbFormEditing" required />
          <label>Драйвер</label>
          <select v-model="dbForm.driver" required>
            <option value="postgresql">postgresql</option>
            <option value="oracle">oracle</option>
          </select>
          <label>Хост</label>
          <input v-model="dbForm.host" required />
          <label>Порт</label>
          <input v-model.number="dbForm.port" type="number" required />
          <label>
            База / service name
            <span v-if="!dbDatabaseRequired" class="label-hint">(необязательно при SID)</span>
          </label>
          <input v-model="dbForm.database" />
          <label>SID <span class="label-hint">(Oracle, опционально)</span></label>
          <input v-model="dbForm.sid" />
          <label>Пользователь</label>
          <input v-model="dbForm.user" required />
          <label>Пароль{{ dbFormEditing ? ' (оставьте пустым, чтобы не менять)' : '' }}</label>
          <input v-model="dbForm.password" type="password" :required="!dbFormEditing" />
          <p v-if="dbFormError" class="error-msg">{{ dbFormError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="closeDbForm">Отмена</button>
            <button type="submit" class="btn-primary" :disabled="savingForm">Сохранить</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="llmFormOpen" class="modal-overlay" @click.self="closeLlmForm">
      <div class="card modal">
        <div class="panel-title">{{ llmForm.alias && llmFormEditing ? 'Изменить LLM' : 'Новый алиас LLM' }}</div>
        <form @submit.prevent="saveLlmForm">
          <label>Алиас</label>
          <input v-model="llmForm.alias" :disabled="llmFormEditing" required />
          <label>Base URL</label>
          <input v-model="llmForm.base_url" required placeholder="http://localhost:11434/v1" />
          <label>Модель</label>
          <input v-model="llmForm.model" required />
          <label>API key{{ llmFormEditing ? ' (оставьте пустым, чтобы не менять)' : '' }}</label>
          <input v-model="llmForm.api_key" type="password" />
          <label>Timeout (сек)</label>
          <input v-model.number="llmForm.timeout" type="number" min="1" />
          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="closeLlmForm">Отмена</button>
            <button type="submit" class="btn-primary" :disabled="savingForm">Сохранить</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  getConnections,
  setDefaultLlmAlias,
  testDbConnection,
  testLlmConnection,
  createDatabaseAlias,
  updateDatabaseAlias,
  deleteDatabaseAlias,
  createLlmAlias,
  updateLlmAlias,
  deleteLlmAlias,
} from '../api/config'

const connections = ref({ databases: [], llm: [], default_llm: null })
const defaultLlmAlias = ref('')
const savingDefaultLlm = ref(false)
const loading = ref(true)
const error = ref('')
const dbTests = ref({})
const llmTests = ref({})

const dbFormOpen = ref(false)
const llmFormOpen = ref(false)
const dbFormEditing = ref(false)
const llmFormEditing = ref(false)
const savingForm = ref(false)
const dbFormError = ref('')

const emptyDbForm = () => ({
  alias: '',
  driver: 'postgresql',
  host: 'localhost',
  port: 5432,
  database: '',
  user: '',
  password: '',
  sid: '',
})

const emptyLlmForm = () => ({
  alias: '',
  base_url: 'http://localhost:11434/v1',
  model: 'gpt-4o-mini',
  api_key: '',
  timeout: 120,
})

const dbForm = ref(emptyDbForm())
const llmForm = ref(emptyLlmForm())

function isOracleDriver(driver) {
  const d = (driver || '').toLowerCase()
  return d === 'oracle' || d === 'oracledb'
}

const dbDatabaseRequired = computed(() => {
  if (!isOracleDriver(dbForm.value.driver)) return true
  return !dbForm.value.sid?.trim()
})

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

function openDbForm(existing = null) {
  dbFormEditing.value = !!existing
  dbFormError.value = ''
  dbForm.value = existing
    ? { ...existing, password: '', sid: existing.sid || '' }
    : emptyDbForm()
  dbFormOpen.value = true
}

function closeDbForm() {
  dbFormOpen.value = false
  dbFormError.value = ''
}

function openLlmForm(existing = null) {
  llmFormEditing.value = !!existing
  llmForm.value = existing
    ? { ...existing, api_key: '' }
    : emptyLlmForm()
  llmFormOpen.value = true
}

function closeLlmForm() {
  llmFormOpen.value = false
}

async function saveDbForm() {
  dbFormError.value = ''
  if (dbDatabaseRequired.value && !dbForm.value.database?.trim()) {
    dbFormError.value = 'Укажите базу / service name'
    return
  }
  savingForm.value = true
  error.value = ''
  try {
    const payload = { ...dbForm.value }
    if (!payload.sid) payload.sid = null
    if (dbFormEditing.value) {
      const { alias, password, ...rest } = payload
      const update = { ...rest }
      if (password) update.password = password
      await updateDatabaseAlias(alias, update)
    } else {
      await createDatabaseAlias(payload)
    }
    await loadConnections()
    closeDbForm()
  } catch (e) {
    error.value = e.message
  } finally {
    savingForm.value = false
  }
}

async function saveLlmForm() {
  savingForm.value = true
  error.value = ''
  try {
    const payload = { ...llmForm.value }
    if (llmFormEditing.value) {
      const { alias, api_key, ...rest } = payload
      const update = { ...rest }
      if (api_key) update.api_key = api_key
      await updateLlmAlias(alias, update)
    } else {
      await createLlmAlias(payload)
    }
    await loadConnections()
    closeLlmForm()
  } catch (e) {
    error.value = e.message
  } finally {
    savingForm.value = false
  }
}

async function removeDb(alias) {
  if (!confirm(`Удалить алиас БД «${alias}»?`)) return
  error.value = ''
  try {
    await deleteDatabaseAlias(alias)
    await loadConnections()
  } catch (e) {
    error.value = e.message
  }
}

async function removeLlm(alias) {
  if (!confirm(`Удалить алиас LLM «${alias}»?`)) return
  error.value = ''
  try {
    await deleteLlmAlias(alias)
    await loadConnections()
  } catch (e) {
    error.value = e.message
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
  max-width: 760px;
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

.btn-small {
  padding: 4px 10px;
  font-size: 12px;
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

.ok-msg { color: var(--success); }

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

.empty {
  font-size: 13px;
  color: var(--text-muted);
}

.setup-hint.inner {
  background: var(--surface2);
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

.label-hint {
  font-weight: 400;
  color: var(--text-muted);
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
