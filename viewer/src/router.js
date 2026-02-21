import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import DatasetView from './views/DatasetView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/dataset', component: DatasetView },
  ],
})
