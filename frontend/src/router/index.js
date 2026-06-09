import { createRouter, createWebHistory } from 'vue-router'
import GeneratorView from '../views/GeneratorView.vue'
import SettingsView from '../views/SettingsView.vue'

const routes = [
  { path: '/', name: 'generator', component: GeneratorView },
  { path: '/settings', name: 'settings', component: SettingsView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
