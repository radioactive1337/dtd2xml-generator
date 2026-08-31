<template>
  <div class="app">
    <header class="app-header">
      <div class="logo">
        <span class="logo-icon">XML</span>
        <span class="logo-text">Генератор XML</span>
      </div>
      <nav class="nav">
        <div class="nav-links">
          <router-link to="/" class="nav-link">Генератор</router-link>
          <router-link to="/settings" class="nav-link">Настройки</router-link>
          <router-link v-if="isAdmin" to="/admin" class="nav-link">Админ</router-link>
          <span class="nav-sep" aria-hidden="true"></span>
          <a :href="UTIL_1_URL" target="_blank" rel="noopener noreferrer" class="nav-link nav-link-external">
            Утилита 1
            <svg class="external-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <path d="M15 3h6v6" />
              <path d="M10 14 21 3" />
            </svg>
          </a>
          <a :href="UTIL_2_URL" target="_blank" rel="noopener noreferrer" class="nav-link nav-link-external">
            Утилита 2
            <svg class="external-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <path d="M15 3h6v6" />
              <path d="M10 14 21 3" />
            </svg>
          </a>
          <a :href="DTD_DOC_URL" target="_blank" rel="noopener noreferrer" class="nav-link nav-link-external">
            DTD документация
            <svg class="external-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <path d="M15 3h6v6" />
              <path d="M10 14 21 3" />
            </svg>
          </a>
        </div>
        <div class="nav-meta">
          <span v-if="user" class="nav-user" :title="user.display_name">{{ user.display_name }}</span>
          <button
            type="button"
            class="nav-icon-btn"
            :title="isDark ? 'Светлая тема' : 'Тёмная тема'"
            :aria-label="isDark ? 'Включить светлую тему' : 'Включить тёмную тему'"
            @click="toggleTheme"
          >
            <svg
              v-if="isDark"
              class="theme-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2.5v2.25" />
              <path d="M12 19.25v2.25" />
              <path d="M4.93 4.93l1.59 1.59" />
              <path d="M17.48 17.48l1.59 1.59" />
              <path d="M2.5 12h2.25" />
              <path d="M19.25 12h2.25" />
              <path d="M4.93 19.07l1.59-1.59" />
              <path d="M17.48 6.52l1.59-1.59" />
            </svg>
            <svg
              v-else
              class="theme-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
            </svg>
          </button>
          <button
            v-if="user"
            type="button"
            class="nav-logout"
            title="Сменить пользователя"
            @click="handleLogout"
          >
            Выйти
          </button>
        </div>
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
const { user, isAdmin, refresh, logout } = useAuth()
const router = useRouter()

// TODO: paste the real utility/DTD documentation URLs here.
// These utilities live on their own origin (not our app) - keeping them as
// plain external links avoids the browser CORS block that hits requests
// made from a page hosted under our domain.
const UTIL_1_URL = 'https://TODO-paste-util-1-link-here'
const UTIL_2_URL = 'https://TODO-paste-util-2-link-here'
const DTD_DOC_URL = 'https://TODO-paste-dtd-doc-link-here'

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
  gap: 16px;
}

.nav-links,
.nav-meta {
  display: inline-flex;
  align-items: center;
}

.nav-links {
  gap: 4px;
}

.nav-meta {
  gap: 8px;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 6px 4px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  color: var(--text-muted);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}

.nav-link:hover {
  color: var(--text);
}

.nav-link.router-link-active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.nav-sep {
  width: 1px;
  height: 18px;
  margin: 0 4px;
  background: var(--border);
}

.nav-link-external {
  gap: 4px;
}

.external-icon {
  width: 12px;
  height: 12px;
  opacity: 0.7;
}

.nav-icon-btn,
.nav-logout {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  transition:
    color 0.15s,
    background 0.15s,
    border-color 0.15s;
}

.nav-icon-btn {
  width: 34px;
  min-width: 34px;
  padding: 0;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-radius: var(--radius);
}

.nav-icon-btn:hover {
  color: var(--text);
  background: var(--surface2);
}

.theme-icon {
  width: 18px;
  height: 18px;
}

.nav-user {
  font-size: 13px;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-logout {
  padding: 6px 10px;
  color: var(--danger);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius);
}

.nav-logout:hover {
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border-color: color-mix(in srgb, var(--danger) 26%, var(--border));
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
