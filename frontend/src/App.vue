<template>
  <div class="app">
    <header class="app-header">
      <div class="logo">
        <span class="logo-icon">XML</span>
        <span class="logo-text">Генератор XML</span>
      </div>
      <nav class="nav">
        <router-link to="/" class="nav-link">Генератор</router-link>
        <router-link to="/settings" class="nav-link">Настройки</router-link>
        <span v-if="user" class="user-badge" :title="user.display_name">{{ user.display_name }}</span>
        <button
          v-if="user"
          class="btn-secondary btn-logout"
          title="Сменить пользователя"
          @click="handleLogout"
        >
          Выйти
        </button>
        <button
          class="theme-toggle"
          :title="isDark ? 'Светлая тема' : 'Тёмная тема'"
          :aria-label="isDark ? 'Включить светлую тему' : 'Включить тёмную тему'"
          @click="toggleTheme"
        >
          <span class="theme-icon" aria-hidden="true">{{ isDark ? '☀' : '☾' }}</span>
        </button>
      </nav>
    </header>
    <main class="app-main">
      <div class="route-wrapper">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from './composables/useTheme'
import { useAuth } from './composables/useAuth'

const { isDark, toggleTheme } = useTheme()
const { user, refresh, logout } = useAuth()
const router = useRouter()

onMounted(() => {
  refresh()
})

async function handleLogout() {
  await logout()
  router.push('/login')
}
</script>

<style scoped>
.app {
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  background: var(--accent);
  color: white;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 8px;
  border-radius: 4px;
}

.logo-text {
  font-weight: 600;
  font-size: 16px;
}

.nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.nav-link {
  color: var(--text-muted);
  text-decoration: none;
  padding: 6px 14px;
  border-radius: var(--radius);
  font-size: 14px;
  transition: all 0.15s;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: var(--text);
  background: var(--surface2);
}

.user-badge {
  font-size: 13px;
  color: var(--text-muted);
  padding: 4px 10px;
  background: var(--surface2);
  border-radius: var(--radius);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-logout {
  padding: 4px 10px;
  font-size: 12px;
}

.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  transition: all 0.15s;
}

.theme-toggle:hover {
  color: var(--text);
  background: var(--surface2);
}

.theme-icon {
  font-size: 16px;
  line-height: 1;
}

.app-main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
}

.route-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
