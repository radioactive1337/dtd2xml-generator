<template>
  <div class="app">
    <header class="app-header">
      <div class="logo">
        <span class="logo-icon">XML</span>
        <span class="logo-text">Генератор XML</span>
      </div>
      <nav class="nav">
        <router-link to="/" class="header-btn">Генератор</router-link>
        <router-link to="/settings" class="header-btn">Настройки</router-link>
        <span v-if="user" class="user-badge" :title="user.display_name">{{ user.display_name }}</span>
        <button
          v-if="user"
          type="button"
          class="header-btn"
          title="Сменить пользователя"
          @click="handleLogout"
        >
          Выйти
        </button>
        <button
          type="button"
          class="header-btn header-btn--icon"
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
        <router-view v-slot="{ Component }">
          <keep-alive include="GeneratorView">
            <component :is="Component" />
          </keep-alive>
        </router-view>
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

.header-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 6px 14px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  color: var(--text);
  text-decoration: none;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  transition: background 0.15s, color 0.15s;
}

.header-btn:hover,
.header-btn.router-link-active {
  background: var(--border);
}

.header-btn--icon {
  width: 34px;
  min-width: 34px;
  padding: 0;
}

.theme-icon {
  font-size: 16px;
  line-height: 1;
}

.user-badge {
  font-size: 13px;
  color: var(--text-muted);
  padding: 6px 12px;
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  background: transparent;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
