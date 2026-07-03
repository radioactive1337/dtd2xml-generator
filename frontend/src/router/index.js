import { createRouter, createWebHistory } from 'vue-router'
import GeneratorView from '../views/GeneratorView.vue'
import SettingsView from '../views/SettingsView.vue'
import LoginView from '../views/LoginView.vue'
import { useAuth } from '../composables/useAuth'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/', name: 'generator', component: GeneratorView },
  { path: '/settings', name: 'settings', component: SettingsView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const { isAuthenticated, checked, refresh } = useAuth()
  if (!checked.value) {
    await refresh()
  }

  if (to.meta.public) {
    if (isAuthenticated.value && to.name === 'login') {
      return { path: '/' }
    }
    return true
  }

  if (!isAuthenticated.value) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
