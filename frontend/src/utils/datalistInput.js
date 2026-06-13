import { ref } from 'vue'

/** Keys of inputs whose datalist dropdown is currently enabled. */
const openKeys = ref(new Set())
const closeTimers = new Map()

export function datalistKey(...parts) {
  return parts.join(':')
}

export function datalistListFor(key, listId) {
  return openKeys.value.has(key) ? listId : undefined
}

export function openDatalist(key) {
  if (!key) return
  clearDatalistCloseTimer(key)
  const next = new Set(openKeys.value)
  next.add(key)
  openKeys.value = next
}

export function closeDatalist(key) {
  if (!key) return
  clearDatalistCloseTimer(key)
  const next = new Set(openKeys.value)
  next.delete(key)
  openKeys.value = next
}

export function scheduleCloseDatalist(key, delayMs = 150) {
  if (!key) return
  clearDatalistCloseTimer(key)
  closeTimers.set(
    key,
    setTimeout(() => {
      closeDatalist(key)
      closeTimers.delete(key)
    }, delayMs),
  )
}

export function clearDatalistCloseTimer(key) {
  const timer = closeTimers.get(key)
  if (timer) {
    clearTimeout(timer)
    closeTimers.delete(key)
  }
}

/** Close dropdown after a confirmed pick (datalist option or valid value). */
export function confirmDatalistPick(key) {
  closeDatalist(key)
}

export function clearAllDatalistState() {
  for (const timer of closeTimers.values()) clearTimeout(timer)
  closeTimers.clear()
  openKeys.value = new Set()
}

export function isOptionSelected(input, options, { caseInsensitive = false } = {}) {
  const value = input?.value?.trim()
  if (!value || !options?.length) return false
  if (caseInsensitive) {
    const lower = value.toLowerCase()
    return options.some((opt) => String(opt).toLowerCase() === lower)
  }
  return options.includes(value)
}
