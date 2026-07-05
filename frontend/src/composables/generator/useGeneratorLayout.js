import { ref, watch, onBeforeUnmount } from 'vue'

const LEFT_PANEL_WIDTH_KEY = 'xml-gen-left-panel-width'
const LEFT_MIN = 480
const LEFT_MAX = 960

function readLeftPanelWidth() {
  try {
    const stored = parseInt(localStorage.getItem(LEFT_PANEL_WIDTH_KEY), 10)
    if (!Number.isNaN(stored)) {
      return Math.max(LEFT_MIN, Math.min(LEFT_MAX, stored))
    }
  } catch {
    // ignore storage errors
  }
  return LEFT_MIN
}

export function useGeneratorLayout() {
  const leftWidth = ref(readLeftPanelWidth())
  const dtdCollapsed = ref(false)

  watch(leftWidth, (val) => {
    try {
      localStorage.setItem(LEFT_PANEL_WIDTH_KEY, String(val))
    } catch {
      // ignore storage errors
    }
  })

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

  onBeforeUnmount(stopResize)

  return { leftWidth, dtdCollapsed, startHResize, stopResize }
}
