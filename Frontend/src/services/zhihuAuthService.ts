import { http } from './http'

export interface ZhihuPublicProfile {
  uid: string
  hash_id: string | null
  fullname: string | null
  headline: string | null
  description: string | null
  avatar_path: string | null
}

export interface ZhihuAuthStatus {
  authenticated: boolean
  configured: boolean
  userApiConfigured: boolean
  user: ZhihuPublicProfile | null
}

export interface ZhihuUserProfile {
  uid: string
  fullname: string
  avatar_path: string
}

/** 读取后端 HttpOnly session 对应的公开认证状态；响应不包含 token。 */
export async function fetchZhihuAuthStatus(): Promise<ZhihuAuthStatus> {
  const response = await http.get<ZhihuAuthStatus>('/auth/zhihu/status')
  return response.data
}

/** 进入后端 OAuth login route；App Key 和 token 不经过浏览器脚本。 */
export function startZhihuLogin() {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')
  window.location.assign(`${baseUrl}/auth/zhihu/login`)
}

/** 获取当前登录用户的公开资料（昵称/头像/uid），token 留在服务端。 */
export async function fetchZhihuUserProfile(): Promise<ZhihuUserProfile> {
  const response = await http.get<ZhihuUserProfile>('/auth/zhihu/profile')
  return response.data
}

/** 清理当前应用会话；不在前端读取或处理 OAuth token。 */
export async function logoutZhihu() {
  await http.post('/auth/zhihu/logout')
}
