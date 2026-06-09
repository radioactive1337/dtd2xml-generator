import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import './style.css'

createApp(App).use(router).mount('#app')
