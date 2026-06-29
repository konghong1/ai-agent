import { create } from 'zustand'

export type ThemeKey = 'techBlue' | 'naturalGreen' | 'elegantPurple'

interface LayoutState {
  collapsed: boolean
  toggleCollapsed: () => void
  theme: ThemeKey
  setTheme: (theme: ThemeKey) => void
  darkMode: boolean
  toggleDarkMode: () => void
}

const savedTheme = (localStorage.getItem('app-theme') as ThemeKey) || 'naturalGreen'
const savedDark = localStorage.getItem('app-dark-mode') === 'true'

export const useLayoutStore = create<LayoutState>((set) => ({
  collapsed: false,
  toggleCollapsed: () => set((s) => ({ collapsed: !s.collapsed })),
  theme: savedTheme,
  setTheme: (theme: ThemeKey) => {
    localStorage.setItem('app-theme', theme)
    set({ theme })
  },
  darkMode: savedDark,
  toggleDarkMode: () => set((s) => {
    const next = !s.darkMode
    localStorage.setItem('app-dark-mode', String(next))
    return { darkMode: next }
  }),
}))
