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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
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
  font-family: ui-monospace, monospace;
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
  font-family: ui-monospace, monospace;
  font-size: 12px;
  background: var(--surface2);
  padding: 1px 5px;
  border-radius: 3px;
}
</style>
