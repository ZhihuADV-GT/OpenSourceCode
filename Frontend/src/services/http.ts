import axios from 'axios'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 5000,
  // Same-origin 请求不受影响；若部署为显式 API origin，确保 HttpOnly session cookie 随请求发送。
  withCredentials: true,
})
