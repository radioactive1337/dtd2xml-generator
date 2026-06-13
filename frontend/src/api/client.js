import axios from 'axios'
import { translateApiError } from '../utils/apiErrors'

const client = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

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

    console.error(
      `[API] ${method || 'REQUEST'} ${url || ''} failed` +
        (status ? ` (${status})` : '') +
        `: ${text}`,
      detail && typeof detail !== 'string' ? { detail } : undefined,
    )

    return Promise.reject(new Error(text))
  },
)

export default client
