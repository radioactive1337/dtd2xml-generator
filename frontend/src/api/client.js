import axios from 'axios'
import { translateApiError } from '../utils/apiErrors'

const client = axios.create({
  baseURL: '/api',
  timeout: 120000,
  withCredentials: true,
})

let loginRedirectPending = false

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = error.config?.url
    const method = error.config?.method?.toUpperCase()
    const detail = error.response?.data?.detail
    const message =
      detail ||
      error.message ||
      'Unknown error'
    const raw = typeof message === 'string' ? message : JSON.stringify(message)
    const text = translateApiError(raw)

    if (
      status === 401 &&
      !url?.includes('/auth/login') &&
      !url?.includes('/auth/me') &&
      !loginRedirectPending &&
      typeof window !== 'undefined' &&
      !window.location.pathname.startsWith('/login')
    ) {
      loginRedirectPending = true
      const redirect = encodeURIComponent(window.location.pathname + window.location.search)
      window.location.assign(`/login?redirect=${redirect}`)
    }

    console.error(
      `[API] ${method || 'REQUEST'} ${url || ''} failed` +
        (status ? ` (${status})` : '') +
        `: ${text}`,
      detail && typeof detail !== 'string' ? { detail } : undefined,
    )

    const err = new Error(text)
    err.response = error.response
    return Promise.reject(err)
  },
)

export default client
