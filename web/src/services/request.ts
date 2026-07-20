import { message } from 'antd'
import { useAuthStore } from '@/stores/auth'

function getToken(): string | null {
  return useAuthStore.getState().token
}

async function jsonSafe(res: Response): Promise<any> {
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

/** Extract a human-readable error message from a fetch Response */
async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const err = await jsonSafe(res)
    return err?.detail || err?.message || `HTTP ${res.status}: 请求失败`
  } catch {
    return `HTTP ${res.status}: 请求失败`
  }
}

export async function request<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let res: Response
  try {
    res = await fetch(path, {
      ...options,
      headers,
      body: options.body && typeof options.body === 'string' ? options.body : undefined,
    })
  } catch (networkErr: any) {
    // ECONNREFUSED / backend down — fetch throws TypeError, not a Response
    const msg = `无法连接到后端服务（请求 ${path} 失败：${networkErr?.message || 'network error'}）。请确认后端是否已启动（端口 8010）`
    message.error(msg, 6)
    throw new Error(msg)
  }

  if (res.status === 401) {
    useAuthStore.getState().logout()
    window.location.href = '/login'
    throw new Error('登录已过期，请重新登录')
  }

  if (!res.ok) {
    const errMsg = await extractErrorMessage(res)
    // Show error popup for all non-OK responses
    message.error(errMsg, 5)
    throw new Error(errMsg)
  }

  if (res.status === 204) return null as T
  const data = await jsonSafe(res)
  return data as T
}

export function get<T = any>(path: string): Promise<T> {
  return request(path)
}

export function post<T = any>(path: string, body?: any): Promise<T> {
  return request(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patch<T = any>(path: string, body?: any): Promise<T> {
  return request(path, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function del<T = any>(path: string): Promise<T> {
  return request(path, { method: 'DELETE' })
}

export function upload<T = any>(path: string, formData: FormData): Promise<T> {
  const token = getToken()
  return fetch(path, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  }).then(async (res) => {
    if (res.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
      throw new Error('登录已过期，请重新登录')
    }
    if (!res.ok) {
      const errMsg = await extractErrorMessage(res)
      message.error(errMsg, 5)
      throw new Error(errMsg)
    }
    return res.json()
  }).catch((err) => {
    // Network error (ECONNREFUSED etc.)
    if (err instanceof TypeError) {
      const msg = `无法连接到后端服务（上传 ${path} 失败：${err.message}）。请确认后端是否已启动（端口 8010）`
      message.error(msg, 6)
      throw new Error(msg)
    }
    throw err
  })
}
