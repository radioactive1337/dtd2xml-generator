import { ref } from 'vue'
import {
  deletePersonalDocument,
  getSharedStatus,
  createPersonalFolder,
  deletePersonalFolder,
  listPersonalDocuments,
  listPersonalFolders,
  listSharedCategories,
  listSharedDocuments,
  loadPersonalDocument,
  loadSharedDocument,
  movePersonalDocument,
  pushDocumentToGit,
  renamePersonalFolder,
  savePersonalDocument,
  shareDocument,
  syncSharedLibrary,
} from '../api/xmlLibrary'
import { translateApiError } from '../utils/apiErrors'

export function useXmlLibrary({ onLoadDocument } = {}) {
  const activeScope = ref('shared')
  const sharedCategories = ref([])
  const sharedDocuments = ref([])
  const personalDocuments = ref([])
  const personalFolders = ref([])
  const selectedCategory = ref(null)
  const syncing = ref(false)
  const gitPushing = ref(false)
  const syncStatus = ref(null)
  const libraryError = ref('')
  const loading = ref(false)

  async function refreshSharedStatus() {
    try {
      syncStatus.value = await getSharedStatus()
    } catch (err) {
      syncStatus.value = { enabled: false }
      libraryError.value = translateApiError(err?.message || String(err))
    }
  }

  async function refreshSharedCategories() {
    libraryError.value = ''
    loading.value = true
    try {
      await refreshSharedStatus()
      if (!syncStatus.value?.enabled) {
        sharedCategories.value = []
        return
      }
      sharedCategories.value = await listSharedCategories()
    } catch (err) {
      libraryError.value = translateApiError(err?.response?.data?.detail || err?.message || String(err))
      sharedCategories.value = []
    } finally {
      loading.value = false
    }
  }

  async function loadCategoryDocuments(category) {
    libraryError.value = ''
    selectedCategory.value = category
    loading.value = true
    try {
      sharedDocuments.value = await listSharedDocuments(category)
    } catch (err) {
      libraryError.value = translateApiError(err?.response?.data?.detail || err?.message || String(err))
      sharedDocuments.value = []
    } finally {
      loading.value = false
    }
  }

  async function syncFromGit() {
    if (syncing.value) return
    libraryError.value = ''
    syncing.value = true
    try {
      const result = await syncSharedLibrary()
      syncStatus.value = {
        ...syncStatus.value,
        enabled: true,
        configured: true,
        last_sync: result.synced_at,
        commit_sha: result.commit_sha,
        message: result.message,
      }
      await refreshSharedCategories()
      if (selectedCategory.value) {
        await loadCategoryDocuments(selectedCategory.value)
      }
      return result
    } catch (err) {
      libraryError.value = translateApiError(err?.response?.data?.detail || err?.message || String(err))
      throw err
    } finally {
      syncing.value = false
    }
  }

  async function pushToGit({
    rootElement,
    filename,
    xmlText,
    schemaId,
    commitMessage = '',
    acknowledgeWarnings = false,
  }) {
    if (gitPushing.value) return
    libraryError.value = ''
    gitPushing.value = true
    try {
      const result = await pushDocumentToGit({
        root_element: rootElement,
        filename,
        xml_text: xmlText,
        schema_id: schemaId,
        commit_message: commitMessage.trim() || null,
        acknowledge_warnings: acknowledgeWarnings,
      })
      if (result.status === 'ok') {
        await refreshSharedCategories()
        if (selectedCategory.value) {
          await loadCategoryDocuments(selectedCategory.value)
        }
      }
      return result
    } finally {
      gitPushing.value = false
    }
  }

  async function reloadPersonalLibrary() {
    const [docs, folders] = await Promise.all([
      listPersonalDocuments(),
      listPersonalFolders(),
    ])
    personalDocuments.value = docs
    personalFolders.value = folders
  }

  async function refreshPersonalDocuments() {
    libraryError.value = ''
    loading.value = true
    try {
      await reloadPersonalLibrary()
    } catch (err) {
      libraryError.value = translateApiError(err?.response?.data?.detail || err?.message || String(err))
      personalDocuments.value = []
      personalFolders.value = []
    } finally {
      loading.value = false
    }
  }

  function reportLibraryError(err) {
    libraryError.value = translateApiError(err?.response?.data?.detail || err?.message || String(err))
  }

  async function createFolder(name) {
    libraryError.value = ''
    try {
      personalFolders.value = await createPersonalFolder(name)
    } catch (err) {
      reportLibraryError(err)
      throw err
    }
  }

  async function renameFolder(name, nextName) {
    libraryError.value = ''
    try {
      await renamePersonalFolder(name, nextName)
      await reloadPersonalLibrary()
    } catch (err) {
      reportLibraryError(err)
      throw err
    }
  }

  async function removeFolder(name) {
    libraryError.value = ''
    try {
      await deletePersonalFolder(name)
      await reloadPersonalLibrary()
    } catch (err) {
      reportLibraryError(err)
      throw err
    }
  }

  async function moveDocumentToFolder(name, folder) {
    libraryError.value = ''
    try {
      await movePersonalDocument(name, folder)
      await reloadPersonalLibrary()
    } catch (err) {
      reportLibraryError(err)
      throw err
    }
  }

  async function openSharedDocument(category, docId) {
    const doc = await loadSharedDocument(category, docId)
    await loadIntoEditor(doc.xml_text)
    return doc
  }

  async function openPersonalDocument(name) {
    const doc = await loadPersonalDocument(name)
    await loadIntoEditor(doc.xml_text)
    return doc
  }

  async function saveCurrentDocument({
    name,
    schemaId,
    xmlText,
    description = '',
    category = 'free-document',
    folder = '',
  }) {
    const payload = {
      name: name.trim(),
      schema_id: schemaId || '',
      category,
      folder: folder || '',
      description: description.trim(),
      xml_text: xmlText,
    }
    const saved = await savePersonalDocument(payload)
    await refreshPersonalDocuments()
    return saved
  }

  async function removePersonalDocument(name) {
    await deletePersonalDocument(name)
    await refreshPersonalDocuments()
  }

  async function sharePersonalDocument(name, recipientUsername, message = '') {
    const result = await shareDocument({
      recipient_username: recipientUsername.trim(),
      source_document_name: name,
      message: message.trim(),
    })
    return result
  }

  async function shareCurrentDocument({
    name,
    schemaId,
    xmlText,
    description = '',
    recipientUsername,
    message = '',
  }) {
    const result = await shareDocument({
      recipient_username: recipientUsername.trim(),
      message: message.trim(),
      document: {
        name: name.trim(),
        schema_id: schemaId || '',
        category: 'free-document',
        description: description.trim(),
        xml_text: xmlText,
      },
    })
    return result
  }

  async function loadIntoEditor(xmlText) {
    if (onLoadDocument) {
      await onLoadDocument(xmlText)
    }
  }

  return {
    activeScope,
    sharedCategories,
    sharedDocuments,
    personalDocuments,
    personalFolders,
    selectedCategory,
    syncing,
    gitPushing,
    syncStatus,
    libraryError,
    loading,
    refreshSharedStatus,
    refreshSharedCategories,
    loadCategoryDocuments,
    syncFromGit,
    pushToGit,
    refreshPersonalDocuments,
    openSharedDocument,
    openPersonalDocument,
    saveCurrentDocument,
    removePersonalDocument,
    createFolder,
    renameFolder,
    removeFolder,
    moveDocumentToFolder,
    sharePersonalDocument,
    shareCurrentDocument,
    loadIntoEditor,
  }
}
