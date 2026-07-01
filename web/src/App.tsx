import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import { useAuthStore } from '@/stores/auth'
import { useLayoutStore } from '@/stores/layout'
import BasicLayout from '@/layouts/BasicLayout'
import LoginLayout from '@/layouts/LoginLayout'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import AgentList from '@/pages/AgentList'
import AgentDetail from '@/pages/AgentDetail'
import KnowledgeBase from '@/pages/KnowledgeBase'
import KBDetail from '@/pages/KnowledgeBase/KBDetail'
import UserManagement from '@/pages/UserManagement'
import MCPManagement from '@/pages/MCPManagement'
import SkillManagement from '@/pages/SkillManagement'
import SettingsPage from '@/pages/Settings'
import ProviderManagement from '@/pages/ProviderManagement'
import './styles/variables.css'
import './styles/global-theme.css'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

const themeToClass: Record<string, string> = {
  techBlue: 'theme-tech-blue',
  naturalGreen: 'theme-natural-green',
  elegantPurple: 'theme-elegant-purple',
}

const themeToPrimary: Record<string, string> = {
  techBlue: '#2563EB',
  naturalGreen: '#22C55E',
  elegantPurple: '#7C3AED',
}

const themeToCardBg: Record<string, string> = {
  techBlue: 'var(--ice-bg-card)',
  naturalGreen: 'var(--ice-bg-card)',
  elegantPurple: 'var(--ice-bg-card)',
}

export default function App() {
  const theme = useLayoutStore((s) => s.theme)
  const darkMode = useLayoutStore((s) => s.darkMode)

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('theme-tech-blue', 'theme-natural-green', 'theme-elegant-purple', 'dark')
    const cls = themeToClass[theme] || ''
    if (cls) root.classList.add(cls)
    if (darkMode) root.classList.add('dark')
  }, [theme, darkMode])

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: themeToPrimary[theme] || '#22C55E',
          colorBgContainer: themeToCardBg[theme] || 'var(--ice-bg-card)',
          borderRadius: 12,
          fontFamily: 'Inter, system-ui, sans-serif',
        },
        algorithm: undefined,
        cssVar: true,
        hashed: false,
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginLayout><Login /></LoginLayout>} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <BasicLayout />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            {/* Agent 聊天页面 */}
            <Route path="agents/chat" element={<AgentDetail />} />
            {/* Agent 管理页面 */}
            <Route path="agents/manage" element={<AgentList />} />
            <Route path="knowledge-bases" element={<KnowledgeBase />} />
            <Route path="knowledge-bases/:id" element={<KBDetail />} />
            <Route path="users" element={<UserManagement />} />
            <Route path="mcp-servers" element={<MCPManagement />} />
            <Route path="skills" element={<SkillManagement />} />
            <Route path="providers" element={<ProviderManagement />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
