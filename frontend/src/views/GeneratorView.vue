<template>
  <div class="generator" ref="generatorRef">
    <div class="generator-left" :style="{ width: leftWidth + 'px' }">
      <div class="dtd-wrapper card">
        <div class="dtd-collapse-header" @click="dtdCollapsed = !dtdCollapsed">
          <span class="panel-title">DTD Schema</span>
          <span class="collapse-arrow" :class="{ rotated: dtdCollapsed }">▼</span>
        </div>
        <div v-show="!dtdCollapsed">
          <DtdUpload @uploaded="onDtdUploaded" />
        </div>
      </div>

      <div v-if="schemaId" class="card controls">
        <div class="panel-title">Generation</div>

        <div class="field">
          <label>Root Element</label>
          <input
            v-model="rootSearch"
            placeholder="Search elements..."
            class="search-input"
          />
          <select v-model="rootElement" size="6" class="element-select">
            <option v-for="el in filteredElements" :key="el" :value="el">{{ el }}</option>
          </select>
        </div>

        <div class="field">
          <label>Build Mode</label>
          <div class="mode-group">
            <label v-for="m in modes" :key="m.value" class="mode-label">
              <input type="radio" v-model="mode" :value="m.value" />
              {{ m.label }}
            </label>
          </div>
        </div>

        <div v-if="mode === 'maximal'" class="field">
          <label>Repeat Count (+ / *)</label>
          <input v-model.number="repeatCount" type="number" min="1" max="100" />
        </div>

        <DtdTreeView
          v-if="mode === 'custom' && rootElement"
          :schema-id="schemaId"
          :root-element="rootElement"
          @update:paths="customPaths = $event"
        />

        <div class="field">
          <label>Populate Strategy</label>
          <select v-model="populateStrategy">
            <option value="faker">Smart Faker</option>
            <option value="llm">AI (LLM)</option>
            <option value="db">Database</option>
          </select>
        </div>

        <div v-if="populateStrategy === 'db'" class="field">
          <label>DB Alias</label>
          <select v-model="dbAlias">
            <option value="">Select alias...</option>
            <option v-for="a in dbAliases" :key="a" :value="a">{{ a }}</option>
          </select>
          <label style="margin-top: 8px">SQL Query</label>
          <textarea
            v-model="sqlQuery"
            rows="3"
            placeholder="SELECT inn, passport FROM clients LIMIT 1"
          />
        </div>

        <div class="action-row">
          <button class="btn-primary" :disabled="!canGenerate || generating" @click="generate">
            {{ generating ? 'Generating...' : 'Generate XML' }}
          </button>
          <button class="btn-secondary" :disabled="!xmlText || populating" @click="populate">
            {{ populating ? 'Populating...' : 'Populate Data' }}
          </button>
        </div>

        <p v-if="error" class="error-msg">{{ error }}</p>
        <p v-if="buildInfo" class="build-info">
          {{ buildInfo.node_count }} nodes
          <span v-if="buildInfo.warnings?.length"> · {{ buildInfo.warnings.length }} warnings</span>
        </p>
      </div>
    </div>

    <div class="col-divider" @mousedown.prevent="startHResize" title="Drag to resize" />

    <div class="generator-right">
      <XmlEditor v-model="xmlText" :filename="`${rootElement || 'generated'}.xml`" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import DtdUpload from '../components/DtdUpload.vue'
import DtdTreeView from '../components/DtdTreeView.vue'
import XmlEditor from '../components/XmlEditor.vue'
import { generateXml } from '../api/generate'
import { populateXml } from '../api/populate'
import { getConfigAliases } from '../api/dtd'

const schemaId = ref('')
const elements = ref([])
const rootElement = ref('')
const rootSearch = ref('')
const mode = ref('minimal')
const repeatCount = ref(1)
const customPaths = ref([])
const populateStrategy = ref('faker')
const dbAlias = ref('')
const sqlQuery = ref('')
const dbAliases = ref([])
const xmlText = ref('')
const buildInfo = ref(null)
const generating = ref(false)
const populating = ref(false)
const error = ref('')

const LEFT_MIN = 440
const LEFT_MAX = 700

const leftWidth = ref(LEFT_MIN)
const dtdCollapsed = ref(false)

watch(mode, (val) => {
  if (val === 'custom') dtdCollapsed.value = true
  else dtdCollapsed.value = false
})

const modes = [
  { value: 'minimal', label: 'Minimal' },
  { value: 'maximal', label: 'Maximal' },
  { value: 'custom', label: 'Custom' },
]

function elementMatchesSearch(elementName, query) {
  const name = elementName.toLowerCase()
  const q = query.toLowerCase().trim().replace(/\s+/g, ' ')
  if (!q) return true
  if (name.includes(q)) return true
  if (name.includes(q.replace(/ /g, '-'))) return true
  return name.replace(/-/g, ' ').includes(q)
}

const filteredElements = computed(() => {
  const q = rootSearch.value
  return elements.value.filter((el) => elementMatchesSearch(el, q))
})

const canGenerate = computed(() => schemaId.value && rootElement.value)

onMounted(async () => {
  try {
    const aliases = await getConfigAliases()
    dbAliases.value = aliases.databases || []
  } catch {
    dbAliases.value = []
  }
})

onBeforeUnmount(() => {
  stopResize()
})

function onDtdUploaded(result) {
  schemaId.value = result.schema_id
  elements.value = result.elements
  rootElement.value = result.elements[0] || ''
  xmlText.value = ''
  buildInfo.value = null
  error.value = ''
}

async function generate() {
  generating.value = true
  error.value = ''
  try {
    const config = {
      schema_id: schemaId.value,
      root_element: rootElement.value,
      mode: mode.value,
      repeat_count: repeatCount.value,
      custom_paths: mode.value === 'custom' ? customPaths.value : [],
    }
    const result = await generateXml(config)
    xmlText.value = result.xml_text
    buildInfo.value = result
  } catch (e) {
    error.value = e.message
  } finally {
    generating.value = false
  }
}

async function populate() {
  populating.value = true
  error.value = ''
  try {
    const request = {
      schema_id: schemaId.value,
      xml_text: xmlText.value,
      strategy: populateStrategy.value,
    }
    if (populateStrategy.value === 'db') {
      request.db_alias = dbAlias.value
      request.sql = sqlQuery.value
    }
    const result = await populateXml(request)
    xmlText.value = result.xml_text
  } catch (e) {
    error.value = e.message
  } finally {
    populating.value = false
  }
}

// ---- Resize logic ----
let activeResize = null
let resizeStartX = 0
let resizeStartVal = 0

function startHResize(e) {
  activeResize = 'h'
  resizeStartX = e.clientX
  resizeStartVal = leftWidth.value
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onResizeMove(e) {
  if (activeResize === 'h') {
    const delta = e.clientX - resizeStartX
    leftWidth.value = Math.max(LEFT_MIN, Math.min(LEFT_MAX, resizeStartVal + delta))
  }
}

function stopResize() {
  activeResize = null
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
</script>

<style scoped>
.generator {
  display: flex;
  align-items: stretch;
  gap: 0;
  height: 100%;
  flex: 1;
  min-height: 0;
}

.generator-left {
  display: flex;
  flex-direction: column;
  gap: 0;
  flex-shrink: 0;
  min-width: 440px;
  height: 100%;
  overflow-y: scroll;
}

.dtd-wrapper {
  /* height is controlled inline when Generation panel is present */
}

.dtd-collapse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: 2px 0 8px;
  user-select: none;
}

.dtd-collapse-header:hover .panel-title {
  color: var(--text);
}

.dtd-collapse-header .panel-title {
  margin-bottom: 0;
  transition: color 0.15s;
}

.collapse-arrow {
  font-size: 11px;
  color: var(--text-muted);
  transition: transform 0.2s ease, color 0.15s;
}

.collapse-arrow.rotated {
  transform: rotate(-90deg);
}


.col-divider {
  width: 8px;
  align-self: stretch;
  cursor: col-resize;
  position: relative;
  flex-shrink: 0;
}

.col-divider::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  transform: translateX(-50%);
  background: var(--border);
  border-radius: 2px;
  transition: background 0.15s;
}

.col-divider:hover::after {
  background: var(--accent);
}

.generator-right {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.search-input {
  margin-bottom: 4px;
}

.element-select {
  height: auto;
}

.mode-group {
  display: flex;
  gap: 12px;
}

.mode-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: var(--text);
  cursor: pointer;
}

.action-row {
  display: flex;
  gap: 8px;
}

.build-info {
  font-size: 12px;
  color: var(--text-muted);
}

@media (max-width: 900px) {
  .generator {
    flex-direction: column;
  }
  .generator-left {
    width: 100% !important;
  }
  .col-divider {
    display: none;
  }
}
</style>
