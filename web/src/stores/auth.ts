import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface User {
  id: number
  email: string
  username: string
  role: string
  is_superuser: boolean
  is_team_admin: boolean
  enabled: boolean
}

interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  permissions: string[]
  login: (email: string, password: string) => Promise<void>
  register: (data: { email: string; username: string; password: string }) => Promise<void>
  logout: () => void
  setUser: (user: User) => void
  loadPermissions: () => Promise<void>
}

async function parseJsonSafe(res: Response): Promise<any> {
  const text = await res.text()
  return text ? JSON.parse(text) : {}
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      permissions: [],

      login: async (email: string, password: string) => {
        let res: Response
        try {
          res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          })
        } catch {
          throw new Error('无法连接到后端服务，请确认后端已启动（端口 8010）')
        }
        if (!res.ok) {
          const err = await parseJsonSafe(res)
          throw new Error(err.detail || `登录失败 (HTTP ${res.status})`)
        }
        const data = await parseJsonSafe(res)
        set({
          token: data.access_token,
          user: data.user,
          isAuthenticated: true,
        })
        await get().loadPermissions()
      },

      register: async (data) => {
        let res: Response
        try {
          res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
          })
        } catch {
          throw new Error('无法连接到后端服务，请确认后端已启动（端口 8010）')
        }
        if (!res.ok) {
          const err = await parseJsonSafe(res)
          throw new Error(err.detail || `注册失败 (HTTP ${res.status})`)
        }
        const result = await parseJsonSafe(res)
        set({
          token: result.access_token,
          user: result.user,
          isAuthenticated: true,
        })
        await get().loadPermissions()
      },

      logout: () => {
        set({ token: null, user: null, isAuthenticated: false, permissions: [] })
      },

      setUser: (user: User) => {
        set({ user, isAuthenticated: true })
      },

      loadPermissions: async () => {
        const token = get().token
        if (!token) {
          set({ permissions: [] })
          return
        }
        try {
          const res = await fetch('/api/me/permissions', {
            headers: { Authorization: `Bearer ${token}` },
          })
          if (res.ok) {
            const d = await res.json()
            set({ permissions: d.permissions || [] })
            return
          }
        } catch {
          // ignore network errors, keep empty
        }
        set({ permissions: [] })
      },
    }),
    { name: 'agent-auth' },
  ),
)
