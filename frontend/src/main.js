import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { initTheme } from './composables/useTheme'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import './style.css'

initTheme()
createApp(App).use(router).mount('#app')
