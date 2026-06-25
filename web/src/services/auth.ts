import { useAuthStore } from '@/stores/auth'

export function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token
  return token
    ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
    : { 'Content-Type': 'application/json' }
}

export function authHeadersRaw(): Record<string, string> {
  const token = useAuthStore.getState().token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function getToken(): string | null {
  return useAuthStore.getState().token
}
