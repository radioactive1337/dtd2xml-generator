<template>
  <div class="tree-view card">
    <div class="tree-header">
      <div class="panel-title">Custom Tree</div>
      <div class="tree-actions">
        <input v-model="presetName" placeholder="Preset name" class="preset-input" />
        <button class="btn-secondary" :disabled="!presetName" @click="savePreset">Save</button>
        <select v-model="loadPresetName" class="preset-select" @change="onLoadPreset">
          <option value="">Load preset...</option>
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
        <div class="tree-row">
          <span class="indent" :style="{ width: `${item.depth * 20}px` }" />
          <button v-if="item.hasChildren" class="expand-btn" @click="toggleExpand(item)">
            {{ item.expanded ? '▼' : '▶' }}
          </button>
          <span v-else class="expand-spacer" />
          <input
            class="tree-checkbox"
            type="checkbox"
            :checked="item.checked"
            :disabled="item.required"
            @change="toggleCheck(item)"
          />
          <span class="node-name" :class="{ required: item.required }">{{ item.name }}</span>
          <span v-if="item.quantifier" class="quantifier">{{ item.quantifier }}</span>
        </div>
      </RecycleScroller>

      <div v-if="loading || !flatNodes.length" class="scroller-hint">
        {{ loading ? 'Loading tree...' : 'Select a root element to load the tree.' }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import { getElementTree } from '../api/dtd'
import { listPresets, savePreset as apiSavePreset, loadPreset as apiLoadPreset } from '../api/presets'

const props = defineProps({
  schemaId: { type: String, required: true },
  rootElement: { type: String, required: true },
})

const emit = defineEmits(['update:paths'])

const treeRoot = ref(null)
const flatNodes = ref([])
const checkedPaths = ref(new Set())
const loading = ref(false)
const presetName = ref('')
const loadPresetName = ref('')
const presets = ref([])
let nodeIdCounter = 0

watch(
  () => [props.schemaId, props.rootElement],
  async () => {
    if (!props.schemaId || !props.rootElement) return
    treeRoot.value = null
    flatNodes.value = []
    checkedPaths.value = new Set()
    await buildInitialTree()
    await refreshPresets()
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

function buildNodeFromModel(name, model, path, depth, required) {
  const quantifier = model.quantifier || ''
  const nodeRequired = required || isRequiredQuantifier(quantifier)
  const node = {
    id: nextId(),
    name,
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
      const childName = child.kind === 'REF' ? child.ref : `group-${idx}`
      const childPath = `${path}.${childName}`
      return buildNodeFromModel(
        childName,
        child,
        childPath,
        depth + 1,
        isRequiredQuantifier(child.quantifier || ''),
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
      const childName = child.kind === 'REF' ? child.ref : `group-${idx}`
      const childPath = `${parentPath}.${childName}`
      return buildNodeFromModel(
        childName,
        child,
        childPath,
        depth,
        isRequiredQuantifier(child.quantifier || ''),
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

function refreshFlat() {
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
    } catch {
      node.hasChildren = false
    } finally {
      loading.value = false
    }
  }

  node.expanded = !node.expanded
  refreshFlat()
}

function toggleCheck(item) {
  if (item.required) return
  const node = findNodeByPath(item.path)
  if (!node) return
  node.checked = !node.checked
  if (node.checked) checkedPaths.value.add(node.path)
  else checkedPaths.value.delete(node.path)
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
}

async function onLoadPreset() {
  if (!loadPresetName.value) return
  const preset = await apiLoadPreset(loadPresetName.value)
  checkedPaths.value = new Set(preset.custom_paths)
  applyCheckedToTree(treeRoot.value)
  refreshFlat()
  emitPaths()
  loadPresetName.value = ''
}

function applyCheckedToTree(node) {
  if (!node) return
  node.checked = node.required || checkedPaths.value.has(node.path)
  for (const child of node.children || []) applyCheckedToTree(child)
}
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
  width: auto !important;
  margin: 0 6px;
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

.quantifier {
  color: var(--accent);
  font-size: 12px;
  font-family: monospace;
  flex-shrink: 0;
  margin-right: 12px;
}

</style>
