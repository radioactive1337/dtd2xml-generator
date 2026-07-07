import { ref } from 'vue'

const HISTORY_KEY = 'xml-gen-history'
const MAX_ENTRIES = 20
// XML larger than this is not persisted to localStorage; the entry is still
// shown in the current session but the xml_text field is omitted on save.
const MAX_XML_PERSIST_BYTES = 256 * 1024 // 256 KB

const history = ref(loadHistory())

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function prepareForStorage(entry) {
  const xmlBytes = entry.xml_text ? new TextEncoder().encode(entry.xml_text).length : 0
  if (xmlBytes > MAX_XML_PERSIST_BYTES) {
    const { xml_text: _dropped, ...rest } = entry
    return rest
  }
  return entry
}

function persistHistory(entries) {
  const list = entries.map(prepareForStorage)
  while (list.length > 0) {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(list))
      return entries
    } catch {
      list.pop()
      entries = entries.slice(0, list.length)
    }
  }
  try {
    localStorage.removeItem(HISTORY_KEY)
  } catch {
    // ignore storage errors
  }
  return []
}

export function useGenerationHistory() {
  function addEntry(entry) {
    const item = {
      id: crypto.randomUUID(),
      timestamp: Date.now(),
      ...entry,
    }
    let next = [item, ...history.value]
    if (next.length > MAX_ENTRIES) {
      next = next.slice(0, MAX_ENTRIES)
    }
    history.value = persistHistory(next)
    return item
  }

  function removeEntry(id) {
    const next = history.value.filter((entry) => entry.id !== id)
    history.value = persistHistory(next)
  }

  function clearHistory() {
    history.value = persistHistory([])
  }

  return { history, addEntry, removeEntry, clearHistory, maxEntries: MAX_ENTRIES }
}
