<template>
  <div class="settings">
    <div class="card">
      <div class="panel-title">Алиасы подключений</div>
      <p class="hint">
        Учётные данные читаются из локального <code>config/connections.json</code>.
        В интерфейсе отображаются только алиасы — секреты не передаются.
        Используйте «Проверить БД» / «Проверить LLM» перед заполнением данных.
      </p>

      <div v-if="loading" class="loading">Загрузка…</div>

      <template v-else>
        <section class="alias-section">
          <h3>Алиасы БД</h3>
          <ul v-if="aliases.databases?.length" class="alias-list">
            <li v-for="db in aliases.databases" :key="db" class="alias-item">
              <span class="alias-icon">DB</span>
              <span class="alias-name">{{ db }}</span>
              <button
                class="btn-secondary btn-test"
                :disabled="isDbTesting(db)"
                @click="testDb(db)"
              >
                {{ isDbTesting(db) ? 'Проверка…' : 'Проверить БД' }}
              </button>
              <span
                v-if="dbStatus(db)"
                class="status-badge"
                :class="dbStatus(db).ok ? 'ok' : 'error'"
                :title="dbStatus(db).message"
              >
                {{ dbStatus(db).ok ? 'OK' : 'Ошибка' }}
              </span>
              <p v-if="dbStatus(db) && !dbStatus(db).ok" class="status-detail error-msg">
                {{ dbStatus(db).message }}
              </p>
              <p v-else-if="dbStatus(db)?.ok" class="status-detail ok-msg">
                {{ dbStatus(db).message }}
              </p>
            </li>
          </ul>
          <p v-else class="empty">Алиасы БД не настроены.</p>
        </section>

        <section class="alias-section">
          <h3>Алиасы LLM</h3>
          <div v-if="aliases.llm?.length > 1" class="default-llm-field">
            <label for="default-llm-select">LLM по умолчанию</label>
            <select
              id="default-llm-select"
              v-model="defaultLlmAlias"
              :disabled="savingDefaultLlm"
              @change="saveDefaultLlm"
            >
              <option v-for="llm in aliases.llm" :key="llm" :value="llm">{{ llm }}</option>
            </select>
            <p class="default-llm-hint">
              Используется при заполнении XML и автосопоставлении полей, если алиас не выбран вручную.
            </p>
          </div>
          <ul v-if="aliases.llm?.length" class="alias-list">
            <li v-for="llm in aliases.llm" :key="llm" class="alias-item">
              <span class="alias-icon llm">LLM</span>
              <span class="alias-name">{{ llm }}</span>
              <button
                class="btn-secondary btn-test"
                :disabled="isLlmTesting(llm)"
                @click="testLlm(llm)"
              >
                {{ isLlmTesting(llm) ? 'Проверка…' : 'Проверить LLM' }}
              </button>
              <span
                v-if="llmStatus(llm)"
                class="status-badge"
                :class="llmStatus(llm).ok ? 'ok' : 'error'"
                :title="llmStatus(llm).message"
              >
                {{ llmStatus(llm).ok ? 'OK' : 'Ошибка' }}
              </span>
              <p v-if="llmStatus(llm) && !llmStatus(llm).ok" class="status-detail error-msg">
                {{ llmStatus(llm).message }}
              </p>
              <p v-else-if="llmStatus(llm)?.ok" class="status-detail ok-msg">
                {{ llmStatus(llm).message }}
              </p>
            </li>
          </ul>
          <p v-else class="empty">Алиасы LLM не настроены.</p>
        </section>

        <section class="setup-hint card inner">
          <div class="panel-title">Настройка</div>
          <ol>
            <li>Скопируйте <code>config/connections.json.example</code> в <code>config/connections.json</code></li>
            <li>Заполните локально учётные данные БД, LLM и Oracle</li>
            <li>Не добавляйте эти файлы в систему контроля версий</li>
          </ol>
        </section>
      </template>

      <p v-if="error" class="error-msg">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getConfigAliases, setDefaultLlmAlias, testDbConnection, testLlmConnection } from '../api/config'

const aliases = ref({ databases: [], llm: [] })
const defaultLlmAlias = ref('')
const savingDefaultLlm = ref(false)
const loading = ref(true)
const error = ref('')
const dbTests = ref({})
const llmTests = ref({})

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

async function testDb(alias) {
  dbTests.value = {
    ...dbTests.value,
    [alias]: { testing: true },
  }
  try {
    const result = await testDbConnection(alias)
    dbTests.value = {
      ...dbTests.value,
      [alias]: { ok: result.ok, message: result.message },
    }
  } catch (e) {
    dbTests.value = {
      ...dbTests.value,
      [alias]: { ok: false, message: e.message },
    }
  }
}

async function testLlm(alias) {
  llmTests.value = {
    ...llmTests.value,
    [alias]: { testing: true },
  }
  try {
    const result = await testLlmConnection(alias)
    llmTests.value = {
      ...llmTests.value,
      [alias]: { ok: result.ok, message: result.message },
    }
  } catch (e) {
    llmTests.value = {
      ...llmTests.value,
      [alias]: { ok: false, message: e.message },
    }
  }
}

async function saveDefaultLlm() {
  if (!defaultLlmAlias.value) return
  const previous = aliases.value.default_llm || aliases.value.llm?.[0] || ''
  savingDefaultLlm.value = true
  error.value = ''
  try {
    const result = await setDefaultLlmAlias(defaultLlmAlias.value)
    aliases.value = {
      ...aliases.value,
      default_llm: result.default_llm,
    }
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
    aliases.value = await getConfigAliases()
    defaultLlmAlias.value = aliases.value.default_llm || aliases.value.llm?.[0] || ''
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.settings {
  max-width: 640px;
}

.hint {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 20px;
  line-height: 1.5;
}

code {
  background: var(--surface2);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.alias-section {
  margin-bottom: 20px;
}

.alias-section h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
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
  margin-bottom: 0;
}

.default-llm-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
  line-height: 1.4;
}

.alias-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.alias-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--surface2);
  border-radius: var(--radius);
  font-size: 14px;
}

.alias-name {
  flex: 1;
  min-width: 80px;
}

.btn-test {
  padding: 4px 10px;
  font-size: 12px;
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
  line-height: 1.4;
}

.ok-msg {
  color: var(--success);
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

.empty {
  font-size: 13px;
  color: var(--text-muted);
}

.setup-hint.inner {
  background: var(--surface2);
  margin-top: 8px;
}

.setup-hint ol {
  padding-left: 20px;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.8;
}

.loading {
  color: var(--text-muted);
  font-size: 14px;
}
</style>
