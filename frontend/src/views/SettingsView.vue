<template>
  <div class="settings">
    <div class="card">
      <div class="panel-title">Connection Aliases</div>
      <p class="hint">
        Credentials are read from local <code>connections.json</code>.
        Only aliases are shown here — no secrets are exposed through the UI.
      </p>

      <div v-if="loading" class="loading">Loading...</div>

      <template v-else>
        <section class="alias-section">
          <h3>Database Aliases</h3>
          <ul v-if="aliases.databases?.length" class="alias-list">
            <li v-for="db in aliases.databases" :key="db" class="alias-item">
              <span class="alias-icon">DB</span>
              {{ db }}
            </li>
          </ul>
          <p v-else class="empty">No database aliases configured.</p>
        </section>

        <section class="alias-section">
          <h3>LLM Aliases</h3>
          <ul v-if="aliases.llm?.length" class="alias-list">
            <li v-for="llm in aliases.llm" :key="llm" class="alias-item">
              <span class="alias-icon llm">LLM</span>
              {{ llm }}
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
import { getConfigAliases } from '../api/dtd'

const aliases = ref({ databases: [], llm: [] })
const loading = ref(true)
const error = ref('')

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
  max-width: 600px;
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
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--surface2);
  border-radius: var(--radius);
  font-size: 14px;
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
