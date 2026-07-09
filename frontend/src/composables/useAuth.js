import { ref, computed } from 'vue'
import * as authApi from '../api/auth'

const user = ref(null)
const checked = ref(false)
const loading = ref(false)

export function useAuth() {
  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => Boolean(user.value?.is_admin))

  async function refresh() {
    loading.value = true
    try {
      user.value = await authApi.fetchMe()
    } catch {
      user.value = null
    } finally {
      checked.value = true
      loading.value = false
    }
  }

  async function checkExists(username) {
    return authApi.checkUsernameExists(username)
  }

  async function login(username, create = false) {
    loading.value = true
    try {
      user.value = await authApi.login(username, create)
      checked.value = true
      return user.value
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    loading.value = true
    try {
      await authApi.logout()
    } finally {
      user.value = null
      loading.value = false
    }
  }

  return {
    user,
    checked,
    loading,
    isAuthenticated,
    isAdmin,
    refresh,
    checkExists,
    login,
    logout,
  }
}
