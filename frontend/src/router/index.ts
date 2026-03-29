import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/chat',
    },
    {
      path: '/chat',
      name: 'Chat',
      component: () => import('../views/ChatView.vue'),
      meta: { title: '问数工作台', icon: 'ChatDotRound' },
    },
    {
      path: '/semantic',
      name: 'Semantic',
      component: () => import('../views/SemanticView_v2.vue'),
      meta: { title: '语义建模', icon: 'Connection' },
    },
    {
      path: '/dashboard',
      name: 'Dashboard',
      component: () => import('../views/DashboardView.vue'),
      meta: { title: '数据资产', icon: 'DataAnalysis' },
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('../views/SettingsView.vue'),
      meta: { title: '系统设置', icon: 'Setting' },
    },
  ],
})

export default router
