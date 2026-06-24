import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface User {
  id: number
  email: string
  username: string
  role: string
}

interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: { email: string; username: string; password: string }) => Promise<void>
  logout: () => void
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isAuthenticated: false,

      login: async (email: string, password: string) => {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        if (!res.ok) {
          const err = await res.json()
          throw new Error(err.detail || 'Login failed')
        }
        const data = await res.json()
        set({
          token: data.access_token,
          user: data.user,
          isAuthenticated: true,
        })
      },

      register: async (data) => {
        const res = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        })
        if (!res.ok) {
          const err = await res.json()
          throw new Error(err.detail || 'Registration failed')
        }
        const result = await res.json()
        set({
          token: result.access_token,
          user: result.user,
          isAuthenticated: true,
        })
      },

      logout: () => {
        set({ token: null, user: null, isAuthenticated: false })
      },

      setUser: (user: User) => {
        set({ user, isAuthenticated: true })
      },
    }),
    { name: 'agent-auth' },
  ),
)
