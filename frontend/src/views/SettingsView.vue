<template>
  <div class="settings">
    <div class="card">
      <div class="panel-title">Connection Aliases</div>
      <p class="hint">
        Credentials are read from local <code>connections.json</code>.
        Only aliases are shown here — no secrets are exposed through the UI.
        Use Test DB / Test LLM to verify connectivity before Fill.
      </p>

      <div v-if="loading" class="loading">Loading...</div>

      <template v-else>
        <section class="alias-section">
          <h3>Database Aliases</h3>
          <ul v-if="aliases.databases?.length" class="alias-list">
            <li v-for="db in aliases.databases" :key="db" class="alias-item">
              <span class="alias-icon">DB</span>
              <span class="alias-name">{{ db }}</span>
              <button
                class="btn-secondary btn-test"
                :disabled="isDbTesting(db)"
                @click="testDb(db)"
              >
                {{ isDbTesting(db) ? 'Testing...' : 'Test DB' }}
              </button>
              <span
                v-if="dbStatus(db)"
                class="status-badge"
                :class="dbStatus(db).ok ? 'ok' : 'error'"
                :title="dbStatus(db).message"
              >
                {{ dbStatus(db).ok ? 'OK' : 'Failed' }}
              </span>
              <p v-if="dbStatus(db) && !dbStatus(db).ok" class="status-detail error-msg">
                {{ dbStatus(db).message }}
              </p>
              <p v-else-if="dbStatus(db)?.ok" class="status-detail ok-msg">
                {{ dbStatus(db).message }}
              </p>
            </li>
          </ul>
          <p v-else class="empty">No database aliases configured.</p>
        </section>

        <section class="alias-section">
          <h3>LLM Aliases</h3>
          <ul v-if="aliases.llm?.length" class="alias-list">
            <li v-for="llm in aliases.llm" :key="llm" class="alias-item">
              <span class="alias-icon llm">LLM</span>
              <span class="alias-name">{{ llm }}</span>
              <button
                class="btn-secondary btn-test"
                :disabled="isLlmTesting(llm)"
                @click="testLlm(llm)"
              >
                {{ isLlmTesting(llm) ? 'Testing...' : 'Test LLM' }}
              </button>
              <span
                v-if="llmStatus(llm)"
                class="status-badge"
                :class="llmStatus(llm).ok ? 'ok' : 'error'"
                :title="llmStatus(llm).message"
              >
                {{ llmStatus(llm).ok ? 'OK' : 'Failed' }}
              </span>
              <p v-if="llmStatus(llm) && !llmStatus(llm).ok" class="status-detail error-msg">
                {{ llmStatus(llm).message }}
              </p>
              <p v-else-if="llmStatus(llm)?.ok" class="status-detail ok-msg">
                {{ llmStatus(llm).message }}
              </p>
            </li>
          </ul>
          <p v-else class="empty">No LLM aliases configured.</p>
        </section>

        <section class="setup-hint card inner">
          <div class="panel-title">Setup</div>
          <ol>
            <li>Copy <code>backend/connections.json.example</code> to <code>connections.json</code></li>
            <li>Fill in your DB, LLM, and Oracle credentials locally</li>
            <li>Never commit these files to version control</li>
          </ol>
        </section>
      </template>

      <p v-if="error" class="error-msg">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getConfigAliases, testDbConnection, testLlmConnection } from '../api/config'

const aliases = ref({ databases: [], llm: [] })
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

onMounted(async () => {
  try {
    aliases.value = await getConfigAliases()
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
  background: rgba(34, 197, 94, 0.15);
  color: var(--success);
}

.status-badge.error {
  background: rgba(239, 68, 68, 0.15);
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
  background: #8b5cf6;
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
