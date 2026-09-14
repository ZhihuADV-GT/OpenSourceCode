import { createRouter, createWebHistory } from 'vue-router'
// [开源版] 知乎 OAuth 认证服务已注释，本地部署无需授权即可游玩
// import { fetchZhihuAuthStatus } from '../services/zhihuAuthService'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: () => import('../views/LandingView.vue'),
    },
    {
      path: '/game',
      name: 'game',
      component: () => import('../views/MapView.vue'),
    },
  ],
})

// [开源版] 知乎 OAuth 强制登录守卫已注释化，本地部署可直接进入 /game
// 原始逻辑：访问 /game 前必须通过知乎 OAuth 认证
// 开发环境可通过 VITE_SKIP_AUTH_GUARD=true 绕过（用于无 OAuth 凭证时的本地测试）
// router.beforeEach(async (to) => {
//   if (to.name === 'game') {
//     // 开发环境降级：环境变量开启时跳过检查
//     const skipGuard = import.meta.env.DEV && import.meta.env.VITE_SKIP_AUTH_GUARD === 'true'
//     if (skipGuard) {
//       return
//     }
//
//     try {
//       const status = await fetchZhihuAuthStatus()
//       if (!status.authenticated) {
//         // 未登录，重定向回 landing 并提示
//         return {
//           name: 'landing',
//           query: { auth_required: '1' },
//         }
//       }
//     } catch {
//       // 后端不可用，也拦回去
//       return {
//         name: 'landing',
//         query: { auth_required: '1', backend_error: '1' },
//       }
//     }
//   }
// })

export default router
