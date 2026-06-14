import { ref, computed } from 'vue'

const THEME_KEY = 'xml-gen-theme'

function getStoredTheme() {
  return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme
}

const theme = ref(getStoredTheme())

export function initTheme() {
  applyTheme(theme.value)
}

export function useTheme() {
  const isDark = computed(() => theme.value === 'dark')

  function setTheme(value) {
    theme.value = value
    localStorage.setItem(THEME_KEY, value)
    applyTheme(value)
  }

  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  return { theme, isDark, setTheme, toggleTheme }
}
