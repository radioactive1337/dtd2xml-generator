<template>
  <div class="tree-view card">
    <div class="tree-header">
      <div class="panel-title">Custom Tree</div>
      <div class="tree-actions">
        <input v-model="presetName" placeholder="Preset name" class="preset-input" />
        <button class="btn-secondary" :disabled="!presetName" @click="savePreset">Save</button>
        <select v-model="loadPresetName" class="preset-select" @change="onLoadPreset">
          <option value="">Select preset...</option>
          <option v-for="p in presets" :key="p.name" :value="p.name">{{ p.name }}</option>
        </select>
      </div>
    </div>

    <div class="scroller-wrap">
      <RecycleScroller
        v-show="flatNodes.length && !loading"
        class="scroller"
        :items="flatNodes"
        :item-size="32"
        key-field="id"
        v-slot="{ item }"
      >
        <div class="tree-row" :key="item.id">
          <span class="indent" :style="{ width: `${item.depth * 20}px` }" />
          <button v-if="item.hasChildren" class="expand-btn" @click="toggleExpand(item)">
            {{ item.expanded ? '▼' : '▶' }}
          </button>
          <span v-else class="expand-spacer" />
          <button
            type="button"
            class="tree-checkbox"
            :class="{ checked: item.checked, disabled: item.required }"
            :disabled="item.required"
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
        {{
          loading
            ? 'Loading tree...'
            : rootElement
              ? 'Building tree...'
              : 'Select a root element or load a preset.'
        }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import { getElementTree } from '../api/dtd'
import { listPresets, savePreset as apiSavePreset, loadPreset as apiLoadPreset } from '../api/presets'
import { inferRootFromElementPaths, normalizeTreePath } from '../utils/xmlPaths'

const props = defineProps({
  schemaId: { type: String, required: true },
  rootElement: { type: String, default: '' },
})

const emit = defineEmits(['update:paths', 'update:rootElement'])

const treeRoot = ref(null)
const flatNodes = ref([])
const checkedPaths = ref(new Set())
const loading = ref(false)
const presetName = ref('')
const loadPresetName = ref('')
const presets = ref([])
const pendingPresetPaths = ref(null)
const pendingXmlPaths = ref(null)
const applyingPresetRoot = ref(false)
let nodeIdCounter = 0

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
      return
    }
    treeRoot.value = null
    flatNodes.value = []
    const preservedPreset = pendingPresetPaths.value
    const preservedXml = pendingXmlPaths.value
    pendingPresetPaths.value = null
    pendingXmlPaths.value = null
    checkedPaths.value = preservedPreset ? new Set(preservedPreset) : new Set()
    await buildInitialTree()
    const xmlPaths = preservedXml ?? pendingXmlPaths.value
    pendingXmlPaths.value = null
    if (xmlPaths) {
      await applyElementPathsToTree(xmlPaths)
    } else if (preservedPreset) {
      applyCheckedToTree(treeRoot.value)
      refreshFlat()
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

async function buildInitialTree() {
  loading.value = true
  try {
    const data = await getElementTree(props.schemaId, props.rootElement)
    treeRoot.value = buildNodeFromModel(
      props.rootElement,
      data.content_model,
      props.rootElement,
      0,
      true,
    )
    treeRoot.value.expanded = true
    refreshFlat()
    emitPaths()
  } finally {
    loading.value = false
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
    checked: nodeRequired,
    expanded: false,
    hasChildren: false,
    children: [],
    _refName: null,
    _loaded: false,
    _isChoiceGroup: model.kind === 'CHOICE',
  }

  if (nodeRequired) checkedPaths.value.add(path)

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

function skipGroupLabelParent(node) {
  let parent = findParentNode(node.path)
  while (parent?.isGroupLabel) {
    parent = findParentNode(parent.path)
  }
  return parent
}

function pruneOrphanPaths() {
  if (!treeRoot.value) return
  for (const path of [...checkedPaths.value]) {
    const node = findNodeByPath(path)
    if (!node || node.required) continue
    let current = node
    while (true) {
      const parent = skipGroupLabelParent(current)
      if (!parent) break
      if (!parent.required && !checkedPaths.value.has(parent.path)) {
        checkedPaths.value.delete(path)
        break
      }
      current = parent
    }
  }
}

function enforceChoiceExclusivity(node = treeRoot.value) {
  if (!node) return
  if (node._isChoiceGroup) {
    const selected = (node.children || []).filter((c) => checkedPaths.value.has(c.path))
    for (let i = 1; i < selected.length; i++) {
      checkedPaths.value.delete(selected[i].path)
    }
  }
  for (const child of node.children || []) enforceChoiceExclusivity(child)
}

function syncCheckedFromPaths(node = treeRoot.value) {
  if (!node) return
  pruneOrphanPaths()
  enforceChoiceExclusivity()
  walkTree(node, (n) => {
    n.checked = n.required || checkedPaths.value.has(n.path)
  })
}

function refreshFlat() {
  syncCheckedFromPaths()
  flatNodes.value = flattenVisible()
}

async function toggleExpand(item) {
  const node = findNodeByPath(item.path)
  if (!node) return

  if (!node._loaded && node._refName) {
    loading.value = true
    try {
      const data = await getElementTree(props.schemaId, node._refName)
      node.children = buildChildrenFromModel(data.content_model, node.path, node.depth + 1)
      node._loaded = true
      node.hasChildren = node.children.length > 0
      syncCheckedFromPaths()
    } catch {
      node.hasChildren = false
    } finally {
      loading.value = false
    }
  }

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
  if (!first || first.required) return
  checkedPaths.value.add(first.path)
  ensureAncestorPaths(first.path)
}

function toggleCheck(path) {
  const node = findNodeByPath(path)
  if (!node || node.required) return

  if (checkedPaths.value.has(node.path)) {
    checkedPaths.value.delete(node.path)
    for (const childPath of collectDescendantPaths(node)) {
      checkedPaths.value.delete(childPath)
    }
  } else {
    checkedPaths.value.add(node.path)
    ensureAncestorPaths(path)
    if (node.isGroupLabel) {
      selectFirstGroupMember(node)
    }
    const parent = findParentNode(path)
    if (parent?._isChoiceGroup) {
      for (const sibling of parent.children) {
        if (sibling.path !== node.path) {
          checkedPaths.value.delete(sibling.path)
          for (const childPath of collectDescendantPaths(sibling)) {
            checkedPaths.value.delete(childPath)
          }
        }
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

async function ensureTreeLoadedForElementPaths(elementPaths) {
  if (!treeRoot.value) return
  const pathSet = new Set(elementPaths)

  function subtreeNeeded(node) {
    const elPath = normalizeTreePath(node.path)
    return [...pathSet].some((p) => p === elPath || p.startsWith(`${elPath}.`))
  }

  async function walkLoad(node) {
    if (subtreeNeeded(node) && node._refName && !node._loaded) {
      loading.value = true
      try {
        const data = await getElementTree(props.schemaId, node._refName)
        node.children = buildChildrenFromModel(data.content_model, node.path, node.depth + 1)
        node._loaded = true
        node.hasChildren = node.children.length > 0
        node.expanded = true
      } finally {
        loading.value = false
      }
    }
    for (const child of node.children || []) {
      await walkLoad(child)
    }
  }

  await walkLoad(treeRoot.value)
}

async function applyElementPathsToTree(elementPaths) {
  if (!treeRoot.value || !elementPaths?.length) return

  const elPathSet = new Set(elementPaths)
  await ensureTreeLoadedForElementPaths(elementPaths)

  const nextChecked = new Set()
  walkTree(treeRoot.value, (node) => {
    if (node.required) nextChecked.add(node.path)
  })

  walkTree(treeRoot.value, (node) => {
    if (node.isGroupLabel) return

    const elPath = normalizeTreePath(node.path)
    if (!elPathSet.has(elPath)) return
    nextChecked.add(node.path)

    let current = node
    while (current) {
      const parent = skipGroupLabelParent(current)
      if (!parent) break
      if (!parent.required) nextChecked.add(parent.path)
      current = parent
    }
  })

  checkedPaths.value = nextChecked
  enforceChoiceExclusivity()
  pruneOrphanPaths()
  expandAncestorsOfChecked()
  refreshFlat()
  emitPaths()
}

async function applyXmlElementPaths(elementPaths) {
  if (!props.schemaId || !elementPaths?.length) return

  const root = inferRootFromElementPaths(elementPaths)
  if (root && root !== props.rootElement) {
    pendingXmlPaths.value = elementPaths
    applyingPresetRoot.value = true
    emit('update:rootElement', root)
    return
  }

  pendingXmlPaths.value = elementPaths
  if (!treeRoot.value) return

  await applyElementPathsToTree(elementPaths)
  pendingXmlPaths.value = null
}

defineExpose({ applyXmlElementPaths })
</script>

<style scoped>
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
  height: 360px;
  position: relative;
}

.scroller {
  height: 100%;
  overflow: auto;
}

.scroller-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 0;
  height: 32px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
  padding-left: 8px;
  overflow: hidden;
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
