<template>
  <div class="tree-view card">
    <div class="tree-header">
      <div class="panel-title">Дерево (свой режим)</div>
      <div class="tree-actions">
        <input v-model="presetName" placeholder="Имя пресета" class="preset-input" />
        <button class="btn-secondary" :disabled="!presetName" @click="savePreset">Сохранить</button>
        <select v-model="loadPresetName" class="preset-select" @change="onLoadPreset">
          <option value="">Выберите пресет…</option>
          <option v-for="p in presets" :key="p.name" :value="p.name">{{ p.name }}</option>
        </select>
      </div>
    </div>

    <div class="scroller-wrap">
      <RecycleScroller
        ref="scrollerRef"
        v-show="flatNodes.length && !loading"
        class="scroller"
        :items="flatNodes"
        :item-size="32"
        key-field="id"
        v-slot="{ item }"
      >
        <div
          class="tree-row"
          :class="{ 'search-highlight': item.path === highlightedPath }"
          :key="item.id"
        >
          <span class="indent" :style="{ width: `${item.depth * 20}px` }" />
          <button v-if="item.hasChildren" class="expand-btn" @click="toggleExpand(item)">
            {{ item.expanded ? '▼' : '▶' }}
          </button>
          <span v-else class="expand-spacer" />
          <button
            type="button"
            class="tree-checkbox"
            :class="{ checked: item.checked, disabled: item.locked }"
            :disabled="item.locked"
            :aria-checked="item.checked"
            role="checkbox"
            @click="toggleCheck(item.path)"
          />
          <span
            class="node-name"
            :class="{ required: item.required, 'group-expr': item.isGroupLabel }"
            :title="item.displayName"
          >{{ item.displayName }}</span>
          <span v-if="item.quantifier" class="quantifier">{{ item.quantifier }}</span>
        </div>
      </RecycleScroller>

      <div v-if="loading || !flatNodes.length" class="scroller-hint">
        <template v-if="loading">
          <span class="tree-spinner" aria-hidden="true" />
          <span>{{ loadingMessage }}</span>
        </template>
        <template v-else>
          {{
            rootElement
              ? 'Построение дерева…'
              : 'Выберите корневой элемент или загрузите пресет.'
          }}
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import { getElementTree } from '../api/dtd'
import { listPresets, savePreset as apiSavePreset, loadPreset as apiLoadPreset } from '../api/presets'
import { inferRootFromElementPaths, normalizeTreePath } from '../utils/xmlPaths'
import { findPathsToElement } from '../utils/dtdTreeNavigation'

const props = defineProps({
  schemaId: { type: String, required: true },
  rootElement: { type: String, default: '' },
})

const emit = defineEmits(['update:paths', 'update:rootElement'])

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
let nodeIdCounter = 0
let loadSeq = 0
let highlightTimer = null

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
  if (!isStale(seq)) loading.value = false
}

onBeforeUnmount(() => {
  cancelPendingLoads()
  if (highlightTimer) clearTimeout(highlightTimer)
})

watch(
  () => props.schemaId,
  async (id) => {
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
      applyCheckedToTree(treeRoot.value)
      refreshFlat()
      endLoad(seq)
    } else {
      refreshFlat()
      emitPaths()
    }
  },
  { immediate: true },
)

function isRequiredQuantifier(q) {
  return q !== '?' && q !== '*'
}

function nextId() {
  return `node-${nodeIdCounter++}`
}

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
    treeRoot.value = buildNodeFromModel(
      props.rootElement,
      model,
      props.rootElement,
      0,
      true,
    )
    treeRoot.value.expanded = true
    flatNodes.value = flattenVisible()
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

function isChoiceChildRequired(parentKind, childQuantifier) {
  // Alternatives in a choice are never all required — user picks at most one.
  if (parentKind === 'CHOICE') return false
  return isRequiredQuantifier(childQuantifier || '')
}

const GROUP_LABEL_MAX = 72

function formatGroupMemberLabel(child) {
  if (child.kind === 'REF') {
    const q = child.quantifier || ''
    return `${child.ref}${q}`
  }
  if (child.kind === 'SEQUENCE' || child.kind === 'CHOICE') {
    return formatGroupLabel(child)
  }
  return child.kind.toLowerCase()
}

function formatGroupLabel(model) {
  const joiner = model.kind === 'CHOICE' ? ' | ' : ', '
  const inner = (model.children || []).map(formatGroupMemberLabel).join(joiner)
  const label = `(${inner})`
  if (label.length <= GROUP_LABEL_MAX) return label
  return `${label.slice(0, GROUP_LABEL_MAX - 1)}…`
}

function nodeDisplayName(name, model) {
  if (name.startsWith('group-') && (model.kind === 'SEQUENCE' || model.kind === 'CHOICE')) {
    return formatGroupLabel(model)
  }
  return name
}

function resolveChildPaths(parentPath, elementPath, parentKind, child, idx) {
  const childName = child.kind === 'REF' ? child.ref : `group-${idx}`
  if (parentKind === 'CHOICE' && child.kind === 'REF') {
    const childPath = `${elementPath}.${child.ref}`
    return { childPath, elementPath: childPath }
  }
  const childPath = `${parentPath}.${childName}`
  const nextElementPath = child.kind === 'REF' ? childPath : elementPath
  return { childPath, elementPath: nextElementPath }
}

function buildNodeFromModel(name, model, path, depth, required, elementPath = null) {
  const elPath = elementPath ?? path
  const quantifier = model.quantifier || ''
  const isGroup = model.kind === 'SEQUENCE' || model.kind === 'CHOICE'
  // REF inside CHOICE has quantifier "" meaning "once if picked", not "mandatory".
  const nodeRequired = isGroup
    ? required || isRequiredQuantifier(quantifier)
    : required
  const node = {
    id: nextId(),
    name,
    displayName: nodeDisplayName(name, model),
    isGroupLabel: name.startsWith('group-'),
    path,
    depth,
    quantifier,
    required: nodeRequired,
    locked: false,
    checked: nodeRequired,
    expanded: false,
    hasChildren: false,
    children: [],
    _refName: null,
    _loaded: false,
    _isChoiceGroup: model.kind === 'CHOICE',
  }

  if (nodeRequired && path === props.rootElement) checkedPaths.value.add(path)

  if (model.kind === 'REF') {
    if (name === model.ref) {
      // This node IS the referenced element; lazy-load its children on expand
      node.hasChildren = true
      node._refName = model.ref
    } else {
      // This node CONTAINS the ref as a direct child (e.g. root element whose
      // entire content model is a single REF like `saldo (saldo-national?)`)
      const childPath = `${path}.${model.ref}`
      const childNode = buildNodeFromModel(
        model.ref,
        model,
        childPath,
        depth + 1,
        isRequiredQuantifier(model.quantifier || ''),
      )
      node.hasChildren = true
      node.children = [childNode]
      node._loaded = true
    }
  } else if (model.kind === 'SEQUENCE' || model.kind === 'CHOICE') {
    node.hasChildren = (model.children || []).length > 0
    node.children = (model.children || []).map((child, idx) => {
      const { childPath, elementPath: childElementPath } = resolveChildPaths(
        path,
        elPath,
        model.kind,
        child,
        idx,
      )
      return buildNodeFromModel(
        child.kind === 'REF' ? child.ref : `group-${idx}`,
        child,
        childPath,
        depth + 1,
        isChoiceChildRequired(model.kind, child.quantifier),
        childElementPath,
      )
    })
    node._loaded = true
  }

  return node
}

function buildChildrenFromModel(model, parentPath, depth) {
  if (model.kind === 'REF') {
    const childPath = `${parentPath}.${model.ref}`
    return [
      buildNodeFromModel(
        model.ref,
        model,
        childPath,
        depth,
        isRequiredQuantifier(model.quantifier || ''),
      ),
    ]
  }
  if (model.kind === 'SEQUENCE' || model.kind === 'CHOICE') {
    return (model.children || []).map((child, idx) => {
      const { childPath, elementPath: childElementPath } = resolveChildPaths(
        parentPath,
        parentPath,
        model.kind,
        child,
        idx,
      )
      return buildNodeFromModel(
        child.kind === 'REF' ? child.ref : `group-${idx}`,
        child,
        childPath,
        depth,
        isChoiceChildRequired(model.kind, child.quantifier),
        childElementPath,
      )
    })
  }
  return []
}

/** Unwrap SEQUENCE(CHOICE) so the REF parent becomes the CHOICE container. */
function normalizeContentModelForTree(model) {
  if (
    model?.kind === 'SEQUENCE'
    && model.children?.length === 1
    && model.children[0].kind === 'CHOICE'
  ) {
    return model.children[0]
  }
  return model
}

/** Apply lazy-loaded content model; mark REF parent as CHOICE container when needed. */
function applyLoadedChildren(node, contentModel) {
  const model = normalizeContentModelForTree(contentModel)
  node.children = buildChildrenFromModel(model, node.path, node.depth + 1)
  node._loaded = true
  node.hasChildren = node.children.length > 0
  node._isChoiceGroup = model.kind === 'CHOICE'
}

function findNodeByPath(path, node = treeRoot.value) {
  if (!node) return null
  if (node.path === path) return node
  for (const child of node.children || []) {
    const found = findNodeByPath(path, child)
    if (found) return found
  }
  return null
}

function findParentNode(path, node = treeRoot.value) {
  if (!node) return null
  for (const child of node.children || []) {
    if (child.path === path) return node
    const found = findParentNode(path, child)
    if (found) return found
  }
  return null
}

function flattenVisible(node = treeRoot.value) {
  const result = []
  if (!node) return result
  function walk(n) {
    result.push(n)
    if (n.expanded) {
      for (const child of n.children || []) walk(child)
    }
  }
  walk(node)
  return result
}

function walkTree(node, fn) {
  if (!node) return
  fn(node)
  for (const child of node.children || []) walkTree(child, fn)
}

function collectDescendantPaths(node) {
  const paths = []
  for (const child of node.children || []) {
    paths.push(child.path)
    paths.push(...collectDescendantPaths(child))
  }
  return paths
}

function removePathAndDescendants(path) {
  checkedPaths.value.delete(path)
  for (const p of [...checkedPaths.value]) {
    if (p !== path && p.startsWith(`${path}.`)) {
      checkedPaths.value.delete(p)
    }
  }
  const node = findNodeByPath(path)
  if (node) {
    for (const childPath of collectDescendantPaths(node)) {
      checkedPaths.value.delete(childPath)
    }
  }
}

function skipGroupLabelParent(node) {
  let parent = findParentNode(node.path)
  // SEQUENCE group labels are UI-only; CHOICE group labels are real branch containers.
  while (parent?.isGroupLabel && !parent._isChoiceGroup) {
    parent = findParentNode(parent.path)
  }
  return parent
}

function pruneOrphanPaths() {
  if (!treeRoot.value) return
  for (const path of [...checkedPaths.value]) {
    const node = findNodeByPath(path)
    if (!node || !isInActiveBranch(node)) {
      checkedPaths.value.delete(path)
    }
  }
}

function findChoiceGroupAncestor(node) {
  let current = node
  while (current) {
    const parent = skipGroupLabelParent(current)
    if (!parent) break
    if (parent._isChoiceGroup) return parent
    current = parent
  }
  return null
}

function findChoiceAlternative(choiceGroup, node) {
  const nodePath = node.path
  for (const alt of choiceGroup.children || []) {
    if (nodePath === alt.path || nodePath.startsWith(`${alt.path}.`)) {
      return alt
    }
  }
  return null
}

function isChoiceAlternativeSelected(choiceGroup, alt) {
  return [...checkedPaths.value].some(
    (p) => p === alt.path || p.startsWith(`${alt.path}.`),
  )
}

/** Required nodes apply only when every ancestor branch is selected (incl. CHOICE alt). */
function isInActiveBranch(node) {
  if (!node) return false
  let current = node
  while (true) {
    const parent = skipGroupLabelParent(current)
    if (!parent) return true

    if (parent._isChoiceGroup) {
      const alt = findChoiceAlternative(parent, current)
      if (!alt || !isChoiceAlternativeSelected(parent, alt)) return false
    }

    if (!parent.required && !checkedPaths.value.has(parent.path)) {
      const hasCheckedDescendant = [...checkedPaths.value].some(
        (p) => p !== parent.path && p.startsWith(`${parent.path}.`),
      )
      if (!hasCheckedDescendant) return false
    }

    current = parent
  }
}

function enforceChoiceExclusivity(node = treeRoot.value) {
  if (!node) return
  if (node._isChoiceGroup) {
    const selected = (node.children || []).filter((c) => isChoiceAlternativeSelected(node, c))
    for (let i = 1; i < selected.length; i++) {
      removePathAndDescendants(selected[i].path)
    }
  }
  for (const child of node.children || []) enforceChoiceExclusivity(child)
}

/** Drop checked paths that belong to non-selected CHOICE alternatives. */
function pruneInactiveChoiceBranches(node = treeRoot.value) {
  if (!node) return
  if (node._isChoiceGroup) {
    for (const alt of node.children || []) {
      if (isChoiceAlternativeSelected(node, alt)) continue
      for (const p of [...checkedPaths.value]) {
        if (p === alt.path || p.startsWith(`${alt.path}.`)) {
          checkedPaths.value.delete(p)
        }
      }
    }
  }
  for (const child of node.children || []) pruneInactiveChoiceBranches(child)
}

function hasCheckedDescendant(node) {
  const prefix = `${node.path}.`
  return [...checkedPaths.value].some((p) => p.startsWith(prefix))
}

function addImpliedAncestorPaths(node = treeRoot.value) {
  walkTree(node, (n) => {
    if (n.isGroupLabel || n.required || !isInActiveBranch(n)) return
    if (hasCheckedDescendant(n)) checkedPaths.value.add(n.path)
  })
}

function syncCheckedFromPaths(node = treeRoot.value) {
  if (!node) return
  pruneOrphanPaths()
  enforceChoiceExclusivity()
  pruneInactiveChoiceBranches(node)
  walkTree(node, (n) => {
    const active = isInActiveBranch(n)
    if (active && n.required) {
      checkedPaths.value.add(n.path)
    } else if (!active) {
      checkedPaths.value.delete(n.path)
    }
  })
  addImpliedAncestorPaths(node)
  enforceChoiceExclusivity()
  pruneInactiveChoiceBranches(node)
  walkTree(node, (n) => {
    const active = isInActiveBranch(n)
    n.locked = active && n.required
    n.checked = active && (n.required || checkedPaths.value.has(n.path))
  })
}

function refreshFlat() {
  syncCheckedFromPaths()
  flatNodes.value = flattenVisible()
}

async function toggleExpand(item) {
  const node = findNodeByPath(item.path)
  if (!node) return

  const seq = loadSeq
  if (!node._loaded && node._refName) {
    beginLoad('Загрузка ветки…')
    try {
      const data = await getElementTree(props.schemaId, node._refName)
      if (seq !== loadSeq) return
      applyLoadedChildren(node, data.content_model)
      syncCheckedFromPaths()
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

function ensureAncestorPaths(path) {
  let current = findNodeByPath(path)
  while (current) {
    const parent = findParentNode(current.path)
    if (!parent) break
    if (!parent.required) {
      checkedPaths.value.add(parent.path)
    }
    current = parent
  }
}

function findFirstSelectableMember(node) {
  if (!node) return null
  if (!node.isGroupLabel) return node
  if (!node.children?.length) return null
  return findFirstSelectableMember(node.children[0])
}

function selectFirstGroupMember(groupNode) {
  const first = findFirstSelectableMember(groupNode)
  if (!first) return
  if (!first.required) checkedPaths.value.add(first.path)
  ensureAncestorPaths(first.path)
}

function toggleCheck(path) {
  const node = findNodeByPath(path)
  if (!node || node.locked) return

  if (checkedPaths.value.has(node.path)) {
    removePathAndDescendants(node.path)
  } else {
    checkedPaths.value.add(node.path)
    ensureAncestorPaths(path)
    if (node.isGroupLabel) {
      selectFirstGroupMember(node)
    }
    const choiceGroup = findChoiceGroupAncestor(node)
    if (choiceGroup) {
      const selectedAlt = findChoiceAlternative(choiceGroup, node)
      for (const sibling of choiceGroup.children) {
        if (selectedAlt && sibling.path === selectedAlt.path) continue
        removePathAndDescendants(sibling.path)
      }
    }
  }

  refreshFlat()
  emitPaths()
}

function emitPaths() {
  emit('update:paths', [...checkedPaths.value])
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

function inferRootFromPaths(paths) {
  if (!paths?.length) return ''
  const tops = paths.filter((p) => !p.includes('.'))
  if (tops.length) return tops[0]
  const shortest = paths.reduce((a, b) => (a.length <= b.length ? a : b))
  return shortest.split('.')[0]
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
    applyCheckedToTree(treeRoot.value)
    refreshFlat()
  }
}

function applyCheckedToTree(node) {
  if (!node) return
  syncCheckedFromPaths(node)
}

function expandAncestorsOfChecked() {
  for (const path of checkedPaths.value) {
    let node = findNodeByPath(path)
    while (node) {
      node.expanded = true
      node = findParentNode(node.path)
    }
  }
}

function addCheckedAncestors(targetSet, node) {
  let current = node
  while (current) {
    const parent = findParentNode(current.path)
    if (!parent) break
    if (!parent.required) targetSet.add(parent.path)
    current = parent
  }
}

function countElPathsUnderAlternative(altNode, elPathSet) {
  const matched = new Set()
  walkTree(altNode, (n) => {
    if (n.isGroupLabel) return
    const el = normalizeTreePath(n.path)
    if (elPathSet.has(el)) matched.add(el)
  })
  // REF/SEQUENCE alts: match element paths by prefix (e.g. user.employee.*)
  if (!altNode.isGroupLabel) {
    const normBase = normalizeTreePath(altNode.path)
    for (const elPath of elPathSet) {
      if (elPath === normBase || elPath.startsWith(`${normBase}.`)) matched.add(elPath)
    }
  }
  return matched.size
}

function resolveChoiceSelectionsFromXml(node, elPathSet, selections = new Map()) {
  if (!node) return selections
  if (node._isChoiceGroup) {
    let bestAlt = null
    let bestScore = 0
    for (const alt of node.children || []) {
      const score = countElPathsUnderAlternative(alt, elPathSet)
      if (score > bestScore) {
        bestScore = score
        bestAlt = alt
      }
    }
    if (bestAlt && bestScore > 0) {
      selections.set(node.path, bestAlt.path)
      resolveChoiceSelectionsFromXml(bestAlt, elPathSet, selections)
    }
    return selections
  }
  for (const child of node.children || []) {
    resolveChoiceSelectionsFromXml(child, elPathSet, selections)
  }
  return selections
}

function isNodeUnderChoiceSelections(node, selections) {
  let current = node
  while (current) {
    const parent = findParentNode(current.path)
    if (!parent) break
    if (parent._isChoiceGroup) {
      const selectedAltPath = selections.get(parent.path)
      if (selectedAltPath) {
        const alt = findChoiceAlternative(parent, current)
        if (!alt || alt.path !== selectedAltPath) return false
      }
    }
    current = parent
  }
  return true
}

function findNodesForElementPath(elPath, node = treeRoot.value, results = []) {
  if (!node) return results
  if (!node.isGroupLabel && normalizeTreePath(node.path) === elPath) {
    results.push(node)
  }
  for (const child of node.children || []) {
    findNodesForElementPath(elPath, child, results)
  }
  return results
}

function pickNodeForElementPath(candidates, selections) {
  if (!candidates.length) return null
  if (candidates.length === 1) return candidates[0]
  const filtered = candidates.filter((n) => isNodeUnderChoiceSelections(n, selections))
  return filtered[0] || null
}

async function loadNodeIfNeeded(node, seq) {
  if (!node?._refName || node._loaded || isStale(seq)) return
  const data = await getElementTree(props.schemaId, node._refName)
  if (isStale(seq)) return
  applyLoadedChildren(node, data.content_model)
}

async function ensureElementPathLoaded(elPath, seq, selections) {
  async function walk(node) {
    if (isStale(seq) || !node) return null
    if (!node.isGroupLabel && normalizeTreePath(node.path) === elPath) return node

    await loadNodeIfNeeded(node, seq)

    for (const child of node.children || []) {
      if (node._isChoiceGroup) {
        const selectedAltPath = selections.get(node.path)
        if (selectedAltPath && child.path !== selectedAltPath) continue
      }
      const found = await walk(child)
      if (found) return found
    }
    return null
  }

  const found = await walk(treeRoot.value)
  if (found) return found

  const candidates = findNodesForElementPath(elPath)
  return pickNodeForElementPath(candidates, selections)
}

async function ensureTreeLoadedForElementPaths(elementPaths, seq) {
  if (!treeRoot.value || isStale(seq)) return
  const pathSet = new Set(elementPaths)

  function subtreeNeeded(node) {
    const elPath = normalizeTreePath(node.path)
    return [...pathSet].some((p) => p === elPath || p.startsWith(`${elPath}.`))
  }

  async function walkLoad(node) {
    if (isStale(seq)) return
    if (subtreeNeeded(node) && node._refName && !node._loaded) {
      const data = await getElementTree(props.schemaId, node._refName)
      if (isStale(seq)) return
      applyLoadedChildren(node, data.content_model)
      node.expanded = true
    }
    for (const child of node.children || []) {
      await walkLoad(child)
    }
  }

  await walkLoad(treeRoot.value)
}

async function applyElementPathsToTree(elementPaths, seq = loadSeq) {
  if (!treeRoot.value || !elementPaths?.length || isStale(seq)) return

  beginLoad('Синхронизация выбора из XML…')
  try {
    const elPathSet = new Set(elementPaths)
    await ensureTreeLoadedForElementPaths(elementPaths, seq)
    if (isStale(seq)) return

    let choiceSelections = resolveChoiceSelectionsFromXml(treeRoot.value, elPathSet)

    const sortedPaths = [...elPathSet].sort(
      (a, b) => a.split('.').length - b.split('.').length,
    )
    for (const elPath of sortedPaths) {
      await ensureElementPathLoaded(elPath, seq, choiceSelections)
      choiceSelections = resolveChoiceSelectionsFromXml(treeRoot.value, elPathSet)
    }
    if (isStale(seq)) return

    choiceSelections = resolveChoiceSelectionsFromXml(treeRoot.value, elPathSet)

    const nextChecked = new Set()
    for (const elPath of elPathSet) {
      const node = await ensureElementPathLoaded(elPath, seq, choiceSelections)
      if (!node || !isNodeUnderChoiceSelections(node, choiceSelections)) continue
      nextChecked.add(node.path)
      addCheckedAncestors(nextChecked, node)
    }

    for (const altPath of choiceSelections.values()) {
      nextChecked.add(altPath)
      const altNode = findNodeByPath(altPath)
      if (altNode) addCheckedAncestors(nextChecked, altNode)
    }

    checkedPaths.value = nextChecked
    enforceChoiceExclusivity()
    pruneOrphanPaths()
    expandAncestorsOfChecked()
    refreshFlat()
    emitPaths()
  } finally {
    endLoad(seq)
  }
}

async function applyXmlElementPaths(elementPaths) {
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

  await applyElementPathsToTree(elementPaths, seq)
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
  applyLoadedChildren(node, data.content_model)
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
      const parent = findNodeByPath(currentPath)
      if (!parent) return false

      const loaded = await loadNodeBranch(parent, seq)
      if (!loaded || seq !== loadSeq) return false

      parent.expanded = true

      const nextPath = parts.slice(0, i + 1).join('.')
      const nextNode = findNodeByPath(nextPath)
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

defineExpose({ applyXmlElementPaths, revealElement })
</script>

<style scoped>
.tree-view {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  overflow: hidden;
}

.tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.tree-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.preset-input { width: 140px; }
.preset-select { width: 150px; }

.scroller-wrap {
  flex: 1 1 auto;
  min-height: 360px;
  min-width: 0;
  position: relative;
}

.scroller {
  height: 100%;
  width: 100%;
  min-width: 0;
  min-height: 0;
}

.scroller :deep(.vue-recycle-scroller__item-wrapper) {
  overflow: hidden;
}

.scroller :deep(.vue-recycle-scroller__item-view) {
  overflow: hidden;
  box-sizing: border-box;
}

.scroller-hint {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 13px;
}

.tree-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid color-mix(in srgb, var(--accent) 20%, var(--border));
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: tree-spin 0.75s linear infinite;
}

@keyframes tree-spin {
  to { transform: rotate(360deg); }
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 0;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  height: 32px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
  padding-left: 8px;
  overflow: hidden;
}

.tree-row.search-highlight {
  background: color-mix(in srgb, var(--accent) 28%, transparent);
  animation: search-highlight-fade 2s ease-out;
}

@keyframes search-highlight-fade {
  0% { background: color-mix(in srgb, var(--accent) 40%, transparent); }
  100% { background: color-mix(in srgb, var(--accent) 28%, transparent); }
}

.indent {
  flex-shrink: 0;
  display: inline-block;
}

.expand-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  padding: 0;
  width: 20px;
  min-width: 20px;
  height: 20px;
  font-size: 10px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.expand-spacer {
  flex-shrink: 0;
  display: inline-block;
  width: 20px;
  min-width: 20px;
}

.tree-checkbox {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  min-width: 16px;
  margin: 0 6px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--bg);
  cursor: pointer;
  position: relative;
}

.tree-checkbox.checked {
  background: var(--accent);
  border-color: var(--accent);
}

.tree-checkbox.checked::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 1px;
  width: 5px;
  height: 9px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

.tree-checkbox.disabled {
  opacity: 0.55;
  cursor: default;
}

.node-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 4px;
}

.node-name.required { font-weight: 600; }

.node-name.group-expr {
  font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  color: var(--text-muted);
}

.quantifier {
  color: var(--accent);
  font-size: 12px;
  font-family: monospace;
  flex-shrink: 0;
  margin-right: 12px;
}

</style>
