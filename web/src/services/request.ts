import { message } from 'antd'
import { useAuthStore } from '@/stores/auth'

function getToken(): string | null {
  return useAuthStore.getState().token
}

async function jsonSafe(res: Response): Promise<any> {
  const text = await res.text()
  return text ? JSON.parse(text) : null
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

  const res = await fetch(path, {
    ...options,
    headers,
    body: options.body && typeof options.body === 'string' ? options.body : undefined,
  })

  if (res.status === 401) {
    useAuthStore.getState().logout()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    const err = await jsonSafe(res)
    throw new Error(err?.detail || 'Request failed')
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
      throw new Error('Unauthorized')
    }
    if (!res.ok) {
      const err = await jsonSafe(res)
      throw new Error(err?.detail || 'Upload failed')
    }
    return res.json()
  })
}
