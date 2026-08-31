<template>
  <div class="admin">
    <div class="card">
      <div class="panel-title">Администрирование</div>
      <p class="hint">
        Управление пользователями, резервное копирование данных и настройки системы.
      </p>

      <div v-if="loading" class="loading">Загрузка…</div>

      <template v-else>
        <section class="admin-section">
          <h3>Система</h3>
          <div v-if="stats" class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ stats.users_count }}</span>
              <span class="stat-label">Пользователей</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ stats.dtd_schemas_count }}</span>
              <span class="stat-label">DTD-схем</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ stats.total_presets }}</span>
              <span class="stat-label">Пресетов</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ stats.total_mapping_presets }}</span>
              <span class="stat-label">Маппингов</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ stats.total_xml_documents }}</span>
              <span class="stat-label">XML-документов</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ formatBytes(stats.data_dir_bytes) }}</span>
              <span class="stat-label">Размер data/</span>
            </div>
          </div>
        </section>

        <section class="admin-section">
          <div class="section-header">
            <h3>Резервное копирование</h3>
            <button
              class="btn-primary btn-small"
              :disabled="backingUp"
              @click="handleBackup"
            >
              {{ backingUp ? 'Создание…' : 'Скачать бэкап' }}
            </button>
          </div>
          <p class="hint section-hint">
            Архив включает каталог <code>data/</code> (пользователи, DTD, пресеты, документы)
            и <code>config/app.json</code>.
          </p>
          <p v-if="backupError" class="error-msg">{{ backupError }}</p>
        </section>

        <section class="admin-section">
          <div class="section-header">
            <h3>Настройки</h3>
          </div>
          <label class="toggle-row">
            <input
              v-model="allowRegistration"
              type="checkbox"
              :disabled="savingSettings"
              @change="saveSettings"
            />
            <span>Разрешить самостоятельную регистрацию новых пользователей</span>
          </label>
          <p v-if="settingsError" class="error-msg">{{ settingsError }}</p>
          <p class="hint section-hint server-config-note">
            Глобальные параметры сервера (Oracle <code>oracle_client_lib_dir</code> и др.) —
            в <code>config/app.json</code> на сервере.
          </p>
        </section>

        <section class="admin-section">
          <div class="section-header">
            <h3>Общие алиасы</h3>
          </div>
          <p class="hint section-hint">
            Подключения БД и LLM общие для всех пользователей. Задать или изменить их может только администратор.
          </p>

          <div class="shared-aliases-block">
            <div class="shared-aliases-header">
              <h4>Алиасы БД</h4>
              <button
                v-if="sharedConnections.databases?.length"
                class="btn-secondary btn-small"
                @click="openDbForm()"
              >
                + Добавить
              </button>
            </div>
            <ul v-if="sharedConnections.databases?.length" class="alias-list">
              <li v-for="db in sharedConnections.databases" :key="db.alias" class="alias-item">
                <span class="alias-icon">DB</span>
                <div class="alias-info">
                  <span class="alias-name">{{ db.alias }}</span>
                  <span class="alias-meta">{{ db.driver }} · {{ db.host }}:{{ db.port }}</span>
                </div>
                <button
                  class="btn-secondary btn-small"
                  :disabled="isDbTesting(db.alias)"
                  @click="testDb(db.alias)"
                >
                  {{ isDbTesting(db.alias) ? 'Проверка…' : 'Проверить' }}
                </button>
                <button class="btn-secondary btn-small" @click="openDbForm(db)">Изменить</button>
                <button class="btn-secondary btn-small danger" @click="removeDb(db.alias)">Удалить</button>
                <span
                  v-if="dbStatus(db.alias) && !isDbTesting(db.alias)"
                  class="status-badge"
                  :class="dbStatus(db.alias).ok ? 'ok' : 'error'"
                >
                  {{ dbStatus(db.alias).ok ? 'OK' : 'Ошибка' }}
                </span>
              </li>
            </ul>
            <div v-else class="aliases-empty">
              <p>Общие алиасы БД не заданы</p>
              <button type="button" class="btn-primary btn-small" @click="openDbForm()">Добавить</button>
            </div>
          </div>

          <div class="shared-aliases-block">
            <div class="shared-aliases-header">
              <h4>Алиасы LLM</h4>
              <button
                v-if="sharedConnections.llm?.length"
                class="btn-secondary btn-small"
                @click="openLlmForm()"
              >
                + Добавить
              </button>
            </div>
            <ul v-if="sharedConnections.llm?.length" class="alias-list">
              <li v-for="llm in sharedConnections.llm" :key="llm.alias" class="alias-item">
                <span class="alias-icon llm">LLM</span>
                <div class="alias-info">
                  <span class="alias-name">{{ llm.alias }}</span>
                  <span class="alias-meta">{{ llm.model }} · {{ llm.base_url }}</span>
                </div>
                <button
                  class="btn-secondary btn-small"
                  :disabled="isLlmTesting(llm.alias)"
                  @click="testLlm(llm.alias)"
                >
                  {{ isLlmTesting(llm.alias) ? 'Проверка…' : 'Проверить' }}
                </button>
                <button class="btn-secondary btn-small" @click="openLlmForm(llm)">Изменить</button>
                <button class="btn-secondary btn-small danger" @click="removeLlm(llm.alias)">Удалить</button>
                <span
                  v-if="llmStatus(llm.alias) && !isLlmTesting(llm.alias)"
                  class="status-badge"
                  :class="llmStatus(llm.alias).ok ? 'ok' : 'error'"
                >
                  {{ llmStatus(llm.alias).ok ? 'OK' : 'Ошибка' }}
                </span>
              </li>
            </ul>
            <div v-else class="aliases-empty">
              <p>Общие алиасы LLM не заданы</p>
              <button type="button" class="btn-primary btn-small" @click="openLlmForm()">Добавить</button>
            </div>
          </div>
          <p v-if="sharedAliasesError" class="error-msg">{{ sharedAliasesError }}</p>
        </section>

        <section class="admin-section">
          <div class="section-header">
            <h3>Пользователи</h3>
            <div class="section-actions">
              <span class="user-count">{{ users.length }} всего</span>
              <button class="btn-secondary btn-small" @click="showAddUser = !showAddUser">
                {{ showAddUser ? 'Отмена' : '+ Добавить' }}
              </button>
            </div>
          </div>

          <form v-if="showAddUser" class="add-user-form" @submit.prevent="handleCreateUser">
            <input
              v-model.trim="newUsername"
              type="text"
              placeholder="Имя пользователя"
              maxlength="64"
              :disabled="creatingUser"
              required
            />
            <button class="btn-primary btn-small" type="submit" :disabled="creatingUser || !newUsername">
              {{ creatingUser ? 'Создание…' : 'Создать' }}
            </button>
          </form>
          <p v-if="createError" class="error-msg">{{ createError }}</p>

          <table v-if="users.length" class="users-table">
            <thead>
              <tr>
                <th>Имя</th>
                <th>Создан</th>
                <th>Последний вход</th>
                <th>Пресеты</th>
                <th>Маппинги</th>
                <th>XML</th>
                <th>Размер</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id" :class="{ 'admin-row': u.is_admin }">
                <td>
                  <span class="user-name">{{ u.display_name }}</span>
                  <span v-if="u.is_admin" class="admin-badge">админ</span>
                </td>
                <td class="mono">{{ formatDate(u.created_at) }}</td>
                <td class="mono">{{ formatDate(u.last_seen) }}</td>
                <td class="num">{{ u.presets_count }}</td>
                <td class="num">{{ u.mapping_presets_count }}</td>
                <td class="num">{{ u.xml_documents_count }}</td>
                <td class="mono">{{ formatBytes(u.workspace_bytes) }}</td>
                <td>
                  <button
                    v-if="!u.is_admin"
                    class="btn-secondary btn-small danger"
                    :disabled="deletingId === u.id"
                    @click="confirmDelete(u)"
                  >
                    {{ deletingId === u.id ? '…' : 'Удалить' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty">Пользователей нет.</p>
          <p v-if="deleteError" class="error-msg">{{ deleteError }}</p>
        </section>
      </template>
    </div>

    <div v-if="dbFormOpen" class="modal-overlay" @click.self="closeDbForm">
      <div class="card modal">
        <div class="panel-title">{{ dbForm.alias && dbFormEditing ? 'Изменить общий БД' : 'Новый общий алиас БД' }}</div>
        <form novalidate @submit.prevent="saveDbForm">
          <label>Алиас</label>
          <input v-model="dbForm.alias" :disabled="dbFormEditing" />
          <label>Драйвер</label>
          <select v-model="dbForm.driver">
            <option value="postgresql">postgresql</option>
            <option value="oracle">oracle</option>
          </select>
          <label>Хост</label>
          <input v-model="dbForm.host" />
          <label>Порт</label>
          <input v-model.number="dbForm.port" type="number" />
          <template v-if="isOracleDriver(dbForm.driver)">
            <label>SID <span class="label-hint">(опционально)</span></label>
            <input v-model="dbForm.sid" autocomplete="off" />
            <label>База / service name</label>
            <input v-model="dbForm.database" autocomplete="off" />
          </template>
          <template v-else>
            <label>База</label>
            <input v-model="dbForm.database" />
          </template>
          <label>Пользователь</label>
          <input v-model="dbForm.user" />
          <label>Пароль{{ dbFormEditing ? ' (оставьте пустым, чтобы не менять)' : '' }}</label>
          <input v-model="dbForm.password" type="password" />
          <p v-if="dbFormError" class="error-msg">{{ dbFormError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="closeDbForm">Отмена</button>
            <button type="submit" class="btn-primary" :disabled="savingAliasForm">Сохранить</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="llmFormOpen" class="modal-overlay" @click.self="closeLlmForm">
      <div class="card modal">
        <div class="panel-title">{{ llmForm.alias && llmFormEditing ? 'Изменить общий LLM' : 'Новый общий алиас LLM' }}</div>
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
            <button type="submit" class="btn-primary" :disabled="savingAliasForm">Сохранить</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, reactive } from 'vue'
import * as adminApi from '../api/admin'

const loading = ref(true)
const stats = ref(null)
const users = ref([])
const allowRegistration = ref(true)
const savingSettings = ref(false)
const settingsError = ref('')
const backingUp = ref(false)
const backupError = ref('')
const deletingId = ref(null)
const deleteError = ref('')
const showAddUser = ref(false)
const newUsername = ref('')
const creatingUser = ref(false)
const createError = ref('')
const sharedConnections = ref({ databases: [], llm: [] })
const sharedAliasesError = ref('')
const dbTests = ref({})
const llmTests = ref({})
const dbFormOpen = ref(false)
const llmFormOpen = ref(false)
const dbFormEditing = ref(false)
const llmFormEditing = ref(false)
const savingAliasForm = ref(false)
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

const dbForm = reactive(emptyDbForm())
const llmForm = reactive(emptyLlmForm())

function isOracleDriver(driver) {
  const d = String(driver ?? '').toLowerCase().trim()
  return d === 'oracle' || d === 'oracledb'
}

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

async function loadSharedConnections() {
  sharedConnections.value = await adminApi.fetchAdminConnections()
}

function openDbForm(existing = null) {
  dbFormEditing.value = !!existing
  dbFormError.value = ''
  const next = existing
    ? { ...emptyDbForm(), ...existing, password: '', sid: existing.sid || '' }
    : emptyDbForm()
  Object.assign(dbForm, next)
  dbFormOpen.value = true
}

function closeDbForm() {
  dbFormOpen.value = false
  dbFormError.value = ''
}

function openLlmForm(existing = null) {
  llmFormEditing.value = !!existing
  const next = existing ? { ...emptyLlmForm(), ...existing, api_key: '' } : emptyLlmForm()
  Object.assign(llmForm, next)
  llmFormOpen.value = true
}

function closeLlmForm() {
  llmFormOpen.value = false
}

function validateDbForm() {
  const sid = String(dbForm.sid ?? '').trim()
  const database = String(dbForm.database ?? '').trim()
  if (!dbForm.alias?.trim()) return 'Укажите алиас'
  if (!dbForm.host?.trim()) return 'Укажите хост'
  if (!dbForm.port) return 'Укажите порт'
  if (isOracleDriver(dbForm.driver)) {
    if (!database && !sid) return 'Укажите базу / service name или SID'
  } else if (!database) {
    return 'Укажите базу'
  }
  if (!dbForm.user?.trim()) return 'Укажите пользователя'
  if (!dbFormEditing.value && !dbForm.password) return 'Укажите пароль'
  return ''
}

async function saveDbForm() {
  dbFormError.value = ''
  const validationError = validateDbForm()
  if (validationError) {
    dbFormError.value = validationError
    return
  }
  savingAliasForm.value = true
  sharedAliasesError.value = ''
  try {
    const payload = { ...dbForm }
    if (!payload.sid?.trim()) payload.sid = null
    else payload.sid = payload.sid.trim()
    if (dbFormEditing.value) {
      const { alias, password, ...rest } = payload
      const update = { ...rest }
      if (password) update.password = password
      await adminApi.updateAdminDatabaseAlias(alias, update)
    } else {
      await adminApi.createAdminDatabaseAlias(payload)
    }
    await loadSharedConnections()
    closeDbForm()
  } catch (err) {
    sharedAliasesError.value = err.message || 'Не удалось сохранить алиас БД'
  } finally {
    savingAliasForm.value = false
  }
}

async function saveLlmForm() {
  savingAliasForm.value = true
  sharedAliasesError.value = ''
  try {
    const payload = { ...llmForm }
    if (llmFormEditing.value) {
      const { alias, api_key, ...rest } = payload
      const update = { ...rest }
      if (api_key) update.api_key = api_key
      await adminApi.updateAdminLlmAlias(alias, update)
    } else {
      await adminApi.createAdminLlmAlias(payload)
    }
    await loadSharedConnections()
    closeLlmForm()
  } catch (err) {
    sharedAliasesError.value = err.message || 'Не удалось сохранить алиас LLM'
  } finally {
    savingAliasForm.value = false
  }
}

async function removeDb(alias) {
  if (!confirm(`Удалить общий алиас БД «${alias}»?`)) return
  sharedAliasesError.value = ''
  try {
    await adminApi.deleteAdminDatabaseAlias(alias)
    await loadSharedConnections()
  } catch (err) {
    sharedAliasesError.value = err.message || 'Не удалось удалить алиас БД'
  }
}

async function removeLlm(alias) {
  if (!confirm(`Удалить общий алиас LLM «${alias}»?`)) return
  sharedAliasesError.value = ''
  try {
    await adminApi.deleteAdminLlmAlias(alias)
    await loadSharedConnections()
  } catch (err) {
    sharedAliasesError.value = err.message || 'Не удалось удалить алиас LLM'
  }
}

async function testDb(alias) {
  dbTests.value = { ...dbTests.value, [alias]: { testing: true } }
  try {
    const result = await adminApi.testAdminDbConnection(alias)
    dbTests.value = { ...dbTests.value, [alias]: { ok: result.ok, message: result.message } }
  } catch (err) {
    dbTests.value = { ...dbTests.value, [alias]: { ok: false, message: err.message } }
  }
}

async function testLlm(alias) {
  llmTests.value = { ...llmTests.value, [alias]: { testing: true } }
  try {
    const result = await adminApi.testAdminLlmConnection(alias)
    llmTests.value = { ...llmTests.value, [alias]: { ok: result.ok, message: result.message } }
  } catch (err) {
    llmTests.value = { ...llmTests.value, [alias]: { ok: false, message: err.message } }
  }
}

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`
}

function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [statsData, usersData, settingsData] = await Promise.all([
      adminApi.fetchAdminStats(),
      adminApi.fetchAdminUsers(),
      adminApi.fetchAdminSettings(),
    ])
    stats.value = statsData
    users.value = usersData.users
    allowRegistration.value = settingsData.allow_self_registration
    await loadSharedConnections()
  } finally {
    loading.value = false
  }
}

async function handleBackup() {
  backingUp.value = true
  backupError.value = ''
  try {
    await adminApi.downloadBackup()
  } catch (err) {
    backupError.value = err.message || 'Не удалось создать бэкап'
  } finally {
    backingUp.value = false
  }
}

async function saveSettings() {
  savingSettings.value = true
  settingsError.value = ''
  try {
    const data = await adminApi.updateAdminSettings({
      allow_self_registration: allowRegistration.value,
    })
    allowRegistration.value = data.allow_self_registration
  } catch (err) {
    settingsError.value = err.message || 'Не удалось сохранить настройки'
  } finally {
    savingSettings.value = false
  }
}

async function handleCreateUser() {
  if (!newUsername.value) return

  creatingUser.value = true
  createError.value = ''
  try {
    const created = await adminApi.createAdminUser(newUsername.value)
    users.value = [...users.value, created].sort((a, b) =>
      a.display_name.localeCompare(b.display_name, 'ru', { sensitivity: 'base' }),
    )
    if (stats.value) {
      stats.value = { ...stats.value, users_count: users.value.length }
    }
    newUsername.value = ''
    showAddUser.value = false
  } catch (err) {
    createError.value = err.message || 'Не удалось создать пользователя'
  } finally {
    creatingUser.value = false
  }
}

async function confirmDelete(user) {
  const ok = window.confirm(
    `Удалить пользователя «${user.display_name}»?\n\nБудут удалены все его пресеты, маппинги и XML-документы. Это действие необратимо.`,
  )
  if (!ok) return

  deletingId.value = user.id
  deleteError.value = ''
  try {
    await adminApi.deleteAdminUser(user.id)
    users.value = users.value.filter((u) => u.id !== user.id)
    if (stats.value) {
      stats.value = { ...stats.value, users_count: users.value.length }
    }
  } catch (err) {
    deleteError.value = err.message || 'Не удалось удалить пользователя'
  } finally {
    deletingId.value = null
  }
}

onMounted(loadAll)
</script>

<style scoped>
.admin {
  max-width: 1100px;
  margin: 0 auto;
  overflow-y: auto;
  height: 100%;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
}

.panel-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
}

.hint {
  color: var(--text-muted);
  font-size: 14px;
  margin-bottom: 20px;
}

.section-hint {
  margin-bottom: 0;
}

.server-config-note {
  margin-top: 12px;
  margin-bottom: 0;
}

.admin-section {
  margin-bottom: 28px;
  padding-bottom: 28px;
  border-bottom: 1px solid var(--border);
}

.admin-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
}

.user-count {
  font-size: 13px;
  color: var(--text-muted);
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.add-user-form {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.add-user-form input {
  flex: 1;
  max-width: 280px;
  padding: 8px 12px;
  font-size: 14px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
}

.add-user-form input:focus {
  outline: none;
  border-color: var(--accent);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.stat-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  cursor: pointer;
}

.toggle-row input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.users-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.users-table th,
.users-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.users-table th {
  color: var(--text-muted);
  font-weight: 500;
  font-size: 12px;
}

.admin-row {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}

.user-name {
  font-weight: 500;
}

.admin-badge {
  display: inline-block;
  margin-left: 8px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 15%, transparent);
  padding: 2px 6px;
  border-radius: 4px;
}

.mono {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.num {
  text-align: center;
}

.btn-small {
  padding: 4px 10px;
  font-size: 12px;
}

.danger {
  color: var(--danger);
  border-color: color-mix(in srgb, var(--danger) 40%, var(--border));
}

.danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--danger) 12%, var(--surface2));
}

.loading,
.empty {
  color: var(--text-muted);
  padding: 20px 0;
}

.error-msg {
  color: var(--danger);
  font-size: 13px;
  margin-top: 8px;
}

code {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--surface2);
  padding: 1px 5px;
  border-radius: 3px;
}

.shared-aliases-block {
  margin-bottom: 20px;
}

.shared-aliases-block:last-of-type {
  margin-bottom: 0;
}

.shared-aliases-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.shared-aliases-header h4 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--text-muted);
}

.alias-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
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

.aliases-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 16px 12px;
  background: var(--surface2);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  text-align: center;
}

.aliases-empty p {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
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
