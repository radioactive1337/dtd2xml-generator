import { ref, computed, shallowRef } from 'vue'
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import { useAuth } from './useAuth'

const STORAGE_KEY = 'xmlgen_collab_session'

const sessionId = ref(null)
const ydoc = shallowRef(null)
const ytext = shallowRef(null)
const provider = shallowRef(null)
const participants = ref([])

function colorFromUserId(userId) {
  let hash = 0
  for (let i = 0; i < userId.length; i += 1) {
    hash = userId.charCodeAt(i) + ((hash << 5) - hash)
  }
  return `hsl(${Math.abs(hash) % 360}, 70%, 50%)`
}

function collabServerUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/collab`
}

function updateParticipantsList() {
  const awareness = provider.value?.awareness
  if (!awareness) {
    participants.value = []
    return
  }

  const seen = new Map()
  awareness.getStates().forEach((state, clientId) => {
    if (!state?.username) return
    const key = state.username
    if (!seen.has(key)) {
      seen.set(key, { username: state.username, color: state.color || '#888' })
    }
    void clientId
  })
  participants.value = [...seen.values()]
}

function setAwarenessState() {
  const { user } = useAuth()
  const awareness = provider.value?.awareness
  if (!awareness || !user.value) return

  awareness.setLocalStateField('username', user.value.display_name)
  awareness.setLocalStateField('color', colorFromUserId(user.value.id || user.value.display_name))
}

function attachProviderListeners(wsProvider) {
  wsProvider.awareness.on('change', updateParticipantsList)
  wsProvider.on('status', () => {
    if (wsProvider.synced) {
      setAwarenessState()
      updateParticipantsList()
    }
  })
}

function connectSession(id, { seedXml = false, initialXml = '' } = {}) {
  if (!id) return null

  const doc = new Y.Doc()
  const text = doc.getText('xml')
  if (seedXml && initialXml) {
    text.insert(0, initialXml)
  }

  const wsProvider = new WebsocketProvider(collabServerUrl(), id, doc, {
    connect: true,
  })

  attachProviderListeners(wsProvider)
  setAwarenessState()

  sessionId.value = id
  ydoc.value = doc
  ytext.value = text
  provider.value = wsProvider

  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // ignore storage errors
  }

  return id
}

export function useCollaboration() {
  const awareness = computed(() => provider.value?.awareness ?? null)
  const isCollaborating = computed(() => Boolean(sessionId.value && provider.value))

  function createSession(initialXml = '') {
    leaveSession()
    const id = crypto.randomUUID()
    connectSession(id, { seedXml: true, initialXml })
    return id
  }

  function joinSession(id) {
    const trimmed = (id || '').trim()
    if (!trimmed) return
    leaveSession()
    connectSession(trimmed)
  }

  function leaveSession() {
    provider.value?.awareness?.off('change', updateParticipantsList)
    provider.value?.destroy()
    ydoc.value?.destroy()

    sessionId.value = null
    ydoc.value = null
    ytext.value = null
    provider.value = null
    participants.value = []

    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // ignore storage errors
    }
  }

  function restoreSession() {
    if (sessionId.value) return
    let stored = ''
    try {
      stored = localStorage.getItem(STORAGE_KEY) || ''
    } catch {
      stored = ''
    }
    if (stored) {
      joinSession(stored)
    }
  }

  return {
    sessionId,
    ydoc,
    ytext,
    provider,
    awareness,
    participants,
    isCollaborating,
    createSession,
    joinSession,
    leaveSession,
    restoreSession,
  }
}
