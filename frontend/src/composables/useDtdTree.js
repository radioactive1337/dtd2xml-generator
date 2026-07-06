import { ref, watch, onBeforeUnmount, onMounted, nextTick } from 'vue'
import { getElementTree, clearElementTreeCache } from '../api/dtd'
import { listPresets, savePreset as apiSavePreset, loadPreset as apiLoadPreset } from '../api/presets'
import { inferRootFromElementPaths, normalizeElementPathsForTreeSync } from '../utils/xmlPaths'
import { findPathsToElement } from '../utils/dtdTreeNavigation'
import {
  applyLoadedChildren,
  buildNodeFromModel,
  createNodeIdFactory,
  findNodeByPath,
  findParentNode,
  flattenVisible,
  normalizeContentModelForTree,
} from '../utils/dtdTree/model'
import {
  syncCheckedFromPaths,
  toggleCheckPath,
} from '../utils/dtdTree/selection'
import {
  buildCheckedPathsFromElementPaths,
  finalizeCheckedPathsFromXml,
  inferRootFromPaths,
} from '../utils/dtdTree/xmlSync'

export function useDtdTree(props, emit) {
  const treeRoot = ref(null)
  const flatNodes = ref([])
  const scrollerRef = ref(null)
  const highlightedPath = ref(null)
  const checkedPaths = ref(new Set())
  const loading = ref(false)
  const loadingMessage = ref('Загрузка дерева…')
  const presetName = ref('')
  const loadPresetName = ref('')
  const presets = ref([])
  const pendingPresetPaths = ref(null)
  const pendingXmlPaths = ref(null)
  const applyingPresetRoot = ref(false)

  let nextId = createNodeIdFactory()
  let loadSeq = 0
  let highlightTimer = null
  let scrollerResizeObserver = null

  function modelOptions() {
    return {
      rootElement: props.rootElement,
      nextId,
      onRequiredRootCheck: (path) => checkedPaths.value.add(path),
    }
  }

  function refreshScrollerLayout() {
    nextTick(() => {
      const scroller = scrollerRef.value
      if (!scroller) return
      scroller.scrollToItem?.(0)
      scroller.updateVisibleItems?.(true)
      window.dispatchEvent(new Event('resize'))
    })
  }

  onMounted(() => {
    const wrap = scrollerRef.value?.$el?.parentElement
    if (wrap && typeof ResizeObserver !== 'undefined') {
      scrollerResizeObserver = new ResizeObserver(() => refreshScrollerLayout())
      scrollerResizeObserver.observe(wrap)
    }
  })

  function isStale(seq) {
    return seq !== loadSeq
  }

  function cancelPendingLoads() {
    loadSeq += 1
    loading.value = false
  }

  function beginLoad(message = 'Загрузка дерева…') {
    loadingMessage.value = message
    loading.value = true
  }

  function endLoad(seq) {
    if (!isStale(seq)) {
      loading.value = false
      refreshScrollerLayout()
    }
  }

  onBeforeUnmount(() => {
    cancelPendingLoads()
    if (highlightTimer) clearTimeout(highlightTimer)
    scrollerResizeObserver?.disconnect()
  })

  watch(
    () => props.schemaId,
    async (id, oldId) => {
      if (oldId) clearElementTreeCache(oldId)
      if (!id) return
      loadPresetName.value = ''
      await refreshPresets()
    },
    { immediate: true },
  )

  watch(
    () => [props.schemaId, props.rootElement],
    async (newVal, oldVal) => {
      const seq = ++loadSeq
      const [, newRoot] = newVal
      const [, oldRoot] = oldVal || []

      if (applyingPresetRoot.value) {
        applyingPresetRoot.value = false
      } else if (oldRoot && newRoot !== oldRoot) {
        loadPresetName.value = ''
      }

      if (!props.schemaId || !props.rootElement) {
        treeRoot.value = null
        flatNodes.value = []
        clearSearchHighlight()
        endLoad(seq)
        return
      }

      clearSearchHighlight()
      treeRoot.value = null
      flatNodes.value = []
      nextId = createNodeIdFactory()

      const preservedPreset = pendingPresetPaths.value
      const preservedXml = pendingXmlPaths.value
      pendingPresetPaths.value = null
      pendingXmlPaths.value = null
      checkedPaths.value = preservedPreset ? new Set(preservedPreset) : new Set()

      const built = await buildInitialTree(seq)
      if (!built || isStale(seq)) return

      const xmlPaths = preservedXml ?? pendingXmlPaths.value
      pendingXmlPaths.value = null
      if (xmlPaths) {
        await applyElementPathsToTree(xmlPaths, seq)
      } else if (preservedPreset) {
        syncCheckedFromPaths(treeRoot.value, checkedPaths.value)
        refreshFlat()
        endLoad(seq)
      } else {
        refreshFlat()
        emitPaths()
      }
    },
    { immediate: true },
  )

  async function refreshPresets() {
    try {
      presets.value = await listPresets()
    } catch {
      presets.value = []
    }
  }

  async function buildInitialTree(seq) {
    beginLoad('Загрузка дерева…')
    try {
      const data = await getElementTree(props.schemaId, props.rootElement)
      if (isStale(seq)) return false
      const model = normalizeContentModelForTree(data.content_model)
      treeRoot.value = buildNodeFromModel({
        name: props.rootElement,
        model,
        path: props.rootElement,
        depth: 0,
        required: true,
        ...modelOptions(),
      })
      treeRoot.value.expanded = true
      flatNodes.value = flattenVisible(treeRoot.value)
      refreshScrollerLayout()
      return true
    } catch {
      if (!isStale(seq)) {
        treeRoot.value = null
        flatNodes.value = []
      }
      return false
    } finally {
      endLoad(seq)
    }
  }

  function refreshFlat() {
    syncCheckedFromPaths(treeRoot.value, checkedPaths.value)
    flatNodes.value = flattenVisible(treeRoot.value)
    refreshScrollerLayout()
  }

  function emitPaths() {
    emit('update:paths', [...checkedPaths.value])
  }

  async function toggleExpand(item) {
    const node = findNodeByPath(item.path, treeRoot.value)
    if (!node) return

    const seq = loadSeq
    if (!node._loaded && node._refName) {
      beginLoad('Загрузка ветки…')
      try {
        const data = await getElementTree(props.schemaId, node._refName)
        if (seq !== loadSeq) return
        applyLoadedChildren(node, data.content_model, modelOptions())
        syncCheckedFromPaths(treeRoot.value, checkedPaths.value)
      } catch {
        if (seq === loadSeq) node.hasChildren = false
      } finally {
        endLoad(seq)
      }
    }

    if (seq !== loadSeq) return
    node.expanded = !node.expanded
    refreshFlat()
  }

  function toggleCheck(path) {
    if (!toggleCheckPath(path, checkedPaths.value, treeRoot.value)) return
    refreshFlat()
    emitPaths()
  }

  async function savePreset() {
    if (!presetName.value) return
    await apiSavePreset({
      name: presetName.value,
      schema_id: props.schemaId,
      custom_paths: [...checkedPaths.value],
    })
    await refreshPresets()
    loadPresetName.value = presetName.value
    presetName.value = ''
  }

  async function onLoadPreset() {
    if (!loadPresetName.value) return
    const preset = await apiLoadPreset(loadPresetName.value)
    const paths = preset.custom_paths || []
    const root = inferRootFromPaths(paths)

    if (!paths.length) return

    checkedPaths.value = new Set(paths)
    emitPaths()

    if (root && root !== props.rootElement) {
      pendingPresetPaths.value = paths
      applyingPresetRoot.value = true
      emit('update:rootElement', root)
      return
    }

    if (treeRoot.value) {
      syncCheckedFromPaths(treeRoot.value, checkedPaths.value)
      refreshFlat()
    }
  }

  async function applyElementPathsToTree(elementPaths, seq = loadSeq, { quiet = false } = {}) {
    if (!treeRoot.value || !elementPaths?.length || isStale(seq)) return

    const syncPaths = normalizeElementPathsForTreeSync(elementPaths)
    const count = syncPaths.length
    if (!quiet) {
      beginLoad(
        count === 1
          ? 'Синхронизация 1 структурного пути…'
          : `Синхронизация ${count} структурных путей…`,
      )
    }
    try {
      const getTree = (elementName) => getElementTree(props.schemaId, elementName)
      const nextChecked = await buildCheckedPathsFromElementPaths({
        elementPaths,
        treeRoot: treeRoot.value,
        getElementTree: getTree,
        isStale: () => isStale(seq),
        preferPaths: new Set(checkedPaths.value),
        modelOptions: modelOptions(),
      })
      if (!nextChecked || isStale(seq)) return

      checkedPaths.value = nextChecked
      finalizeCheckedPathsFromXml(checkedPaths.value, treeRoot.value)
      refreshFlat()
      emitPaths()
    } finally {
      if (!quiet) endLoad(seq)
    }
  }

  async function applyXmlElementPaths(elementPaths, { quiet = false } = {}) {
    if (!props.schemaId || !elementPaths?.length) return

    const seq = loadSeq
    const root = inferRootFromElementPaths(elementPaths)
    if (root && root !== props.rootElement) {
      pendingXmlPaths.value = elementPaths
      applyingPresetRoot.value = true
      emit('update:rootElement', root)
      return
    }

    pendingXmlPaths.value = elementPaths
    if (!treeRoot.value) return

    await applyElementPathsToTree(elementPaths, seq, { quiet })
    if (!isStale(seq)) pendingXmlPaths.value = null
  }

  function clearSearchHighlight() {
    highlightedPath.value = null
    if (highlightTimer) {
      clearTimeout(highlightTimer)
      highlightTimer = null
    }
  }

  function flashSearchHighlight(path) {
    clearSearchHighlight()
    highlightedPath.value = path
    highlightTimer = setTimeout(() => {
      highlightedPath.value = null
      highlightTimer = null
    }, 2000)
  }

  function scrollToTreePath(path) {
    const index = flatNodes.value.findIndex((n) => n.path === path)
    if (index < 0) return
    const scroller = scrollerRef.value
    if (scroller?.scrollToItem) {
      scroller.scrollToItem(index)
    }
  }

  async function loadNodeBranch(node, seq) {
    if (!node?._refName || node._loaded) return true
    const data = await getElementTree(props.schemaId, node._refName)
    if (seq !== loadSeq) return false
    applyLoadedChildren(node, data.content_model, modelOptions())
    return true
  }

  async function revealPath(path) {
    if (!treeRoot.value || !path?.trim()) return false

    const seq = loadSeq
    const parts = path.split('.')
    if (parts[0] !== treeRoot.value.name) return false

    beginLoad('Поиск в дереве…')
    try {
      let currentPath = treeRoot.value.path

      for (let i = 1; i < parts.length; i++) {
        const parent = findNodeByPath(currentPath, treeRoot.value)
        if (!parent) return false

        const loaded = await loadNodeBranch(parent, seq)
        if (!loaded || seq !== loadSeq) return false

        parent.expanded = true

        const nextPath = parts.slice(0, i + 1).join('.')
        const nextNode = findNodeByPath(nextPath, treeRoot.value)
        if (!nextNode) return false
        currentPath = nextPath
      }

      if (seq !== loadSeq) return false

      refreshFlat()
      await nextTick()
      scrollToTreePath(path)
      flashSearchHighlight(path)
      return true
    } finally {
      endLoad(seq)
    }
  }

  async function revealElement(name) {
    const target = name?.trim()
    if (!target) {
      return { ok: false, error: 'Укажите имя элемента' }
    }
    if (!props.schemaId || !props.rootElement) {
      return { ok: false, error: 'Выберите корневой элемент' }
    }
    if (!treeRoot.value) {
      return { ok: false, error: 'Дерево ещё не загружено' }
    }

    clearSearchHighlight()

    const path = await findPathsToElement(
      props.rootElement,
      target,
      (elementName) => getElementTree(props.schemaId, elementName),
    )

    if (!path) {
      return {
        ok: false,
        error: `Элемент «${target}» не достижим от корня «${props.rootElement}»`,
      }
    }

    const revealed = await revealPath(path)
    if (!revealed) {
      return { ok: false, error: 'Не удалось раскрыть путь в дереве' }
    }

    return { ok: true, path }
  }

  return {
    flatNodes,
    scrollerRef,
    highlightedPath,
    loading,
    loadingMessage,
    presetName,
    loadPresetName,
    presets,
    toggleExpand,
    toggleCheck,
    savePreset,
    onLoadPreset,
    applyXmlElementPaths,
    revealElement,
  }
}
