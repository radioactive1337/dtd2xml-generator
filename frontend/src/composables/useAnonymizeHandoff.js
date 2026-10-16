import { ref } from 'vue'

/**
 * In-memory hand-off of an anonymized XML from the anonymization page to the
 * Generator. Lives only in module state: never in localStorage / URL / server.
 */
const pending = ref(null)

export function useAnonymizeHandoff() {
  function offerToGenerator(xmlText) {
    pending.value = { xmlText, at: Date.now() }
  }

  /** Returns the pending XML once and clears it. */
  function consume() {
    const value = pending.value?.xmlText ?? null
    pending.value = null
    return value
  }

  return { pending, offerToGenerator, consume }
}
