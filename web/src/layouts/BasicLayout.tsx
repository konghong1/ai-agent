import { useEffect, useState, useMemo } from "react"

import { Outlet, useNavigate, useLocation } from "react-router-dom"

import { Layout, Menu, Avatar, Button, Space, Typography, Dropdown } from "antd"

import {

  DashboardOutlined, RobotOutlined, TeamOutlined,

  SettingOutlined, SafetyOutlined,

  MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined, LogoutOutlined,

  SunOutlined, MoonOutlined, CloudServerOutlined, AppstoreOutlined, DatabaseOutlined,

} from "@ant-design/icons"

import { useAuthStore } from "@/stores/auth"

import { useLayoutStore } from "@/stores/layout"

import { ParticleBg } from "@/components/ParticleBg"

import { RobotLogo } from "@/components/RobotLogo"



const { Sider, Header, Content } = Layout

const { Text } = Typography



const menuItems = [

  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },

  {

    key: "/agent",

    icon: <RobotOutlined />,

    label: "Agent",

    children: [

      { key: "/agents/chat", label: "聊天" },

      { key: "/providers", label: "AI 提供商" },

      { key: "/mcp-servers", label: "MCP Server" },

      { key: "/skills", label: "Skills" },

      { key: "/hooks", label: "Hooks" },

      { key: "/prompt-templates", label: "提示词模板" },

    ],

  },

  {

    key: "/resources",

    icon: <CloudServerOutlined />,

    label: "资源中心",

    children: [

      { key: "/knowledge-bases", label: "知识库" },
      { key: "/media-library", label: "媒体库" },

    ],

  },

  { key: "/users", icon: <TeamOutlined />, label: "用户管理" },

  { key: "/admin/team-admins", icon: <SettingOutlined />, label: "团队管理员权限" },

  { key: "/teams", icon: <TeamOutlined />, label: "团队" },

  {
    key: "/workbench",
    icon: <AppstoreOutlined />,
    label: "工作台",
    children: [
      { key: "/ecommerce-gallery", label: "电商套图" },
    ],
  },

  { key: "/memory", icon: <DatabaseOutlined />, label: "长期记忆" },

  { key: "/settings", icon: <SettingOutlined />, label: "系统设置" },

]



// 菜单项 → 可见性权限码。未列出的项始终可见（如仪表盘/系统设置）。
const MENU_PERM: Record<string, string> = {
  "/users": "admin.users.manage",
  "/admin/team-admins": "admin.permissions.manage",
  "/teams": "team.view",
  "/mcp-servers": "mcp.view",
  "/skills": "skill.view",
  "/hooks": "hook.view",
  "/knowledge-bases": "kb.read",
  "/media-library": "media.use",
  "/ecommerce-gallery": "gallery.use",
  "/memory": "memory.use",
  "/providers": "providers.view",
  "/prompt-templates": "prompt.view",
}

function filterMenuByPerm(items: any[], perms: string[]): any[] {
  const out: any[] = []
  for (const it of items) {
    if (it.children) {
      const kids = it.children.filter((c: any) => !MENU_PERM[c.key] || perms.includes(MENU_PERM[c.key]))
      if (kids.length > 0) out.push({ ...it, children: kids })
    } else if (!MENU_PERM[it.key] || perms.includes(MENU_PERM[it.key])) {
      out.push(it)
    }
  }
  return out
}

// 动态菜单：后端 resources(type='menu') 驱动。图标名 → 组件映射（未知图标回退 AppstoreOutlined）。
const ICONS: Record<string, any> = {
  DashboardOutlined, RobotOutlined, TeamOutlined, SettingOutlined, SafetyOutlined,
  CloudServerOutlined, AppstoreOutlined, DatabaseOutlined,
}
function convertMenus(nodes: any[]): any[] {
  return (nodes || []).map((n: any) => {
    const Ico = n.icon && ICONS[n.icon] ? ICONS[n.icon] : null
    return {
      key: n.key,
      label: n.label,
      icon: Ico ? <Ico /> : undefined,
      children: n.children && n.children.length ? convertMenus(n.children) : undefined,
    }
  })
}

export default function BasicLayout() {

  const navigate = useNavigate()

  const location = useLocation()

  const isChatPage = location.pathname === "/agents/chat"
  const isGalleryPage = location.pathname === "/ecommerce-gallery"

  const { collapsed, toggleCollapsed } = useLayoutStore()

  const { darkMode, toggleDarkMode } = useLayoutStore()

  const { user, logout, permissions, loadPermissions } = useAuthStore()

  // 动态菜单：拉取后端菜单树（resources 驱动）；失败时回退静态菜单（防白屏）
  const [dynamicMenus, setDynamicMenus] = useState<any[] | null>(null)
  useEffect(() => {
    let cancelled = false
    const token = useAuthStore.getState().token
    if (!token) return
    fetch("/api/system/menus", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { if (!cancelled) setDynamicMenus(convertMenus(d.menus || [])) })
      .catch(() => { if (!cancelled) setDynamicMenus(null) })
    return () => { cancelled = true }
  }, [])

  // 挂载时拉取当前用户的有效权限（用于权限驱动菜单渲染 + 静态 fallback）
  useEffect(() => {
    loadPermissions()
  }, [loadPermissions])

  const visibleMenuItems = useMemo(
    () => dynamicMenus ?? (user?.is_superuser ? menuItems : filterMenuByPerm(menuItems, permissions)),
    [user, permissions, dynamicMenus],
  )

  const [mobileOpen, setMobileOpen] = useState(false)
  const [winWidth, setWinWidth] = useState(typeof window !== "undefined" ? window.innerWidth : 1280)



  useEffect(() => {

    setMobileOpen(false)

  }, [location.pathname])



  useEffect(() => {

    const handleResize = () => {

      setWinWidth(window.innerWidth)
      if (window.innerWidth < 768) {

        setMobileOpen(false)

      }

    }

    window.addEventListener("resize", handleResize)

    return () => window.removeEventListener("resize", handleResize)

  }, [])



  const isMobile = typeof window !== "undefined" && window.innerWidth < 768

  // 与 Sider 实际折叠状态保持一致：桌面端跟随 store，移动端抽屉打开时为展开
  const siderCollapsed = isMobile ? !mobileOpen : collapsed



  const userMenu = {

    items: [

      { key: "username", label: <Text style={{ color: "var(--ice-text-primary)" }}>{user?.username}</Text>, disabled: true },

      { type: "divider" as const },

      { key: "logout", icon: <LogoutOutlined />, label: "退出登录",

        onClick: () => { logout(); navigate("/login") } },

    ],

  }



  return (

    <Layout className="main-layout" style={{ minHeight: "100vh" }}>

      <ParticleBg count={25} speed={0.2} opacity={0.2} />

      <Sider

        collapsed={isMobile ? mobileOpen : collapsed}

        width={256}

        collapsedWidth={80}

        style={{

          background: "var(--ice-bg-secondary)",

          borderRight: "1px solid var(--ice-border)",

          zIndex: 1000,

          position: isMobile ? "fixed" : "relative",

          top: 0,

          left: 0,

          height: "100vh",

          visibility: isMobile && !mobileOpen ? "hidden" : "visible",

        }}

      >

        {/* Logo 区域：3D 动画机器人图标 + 平台名称，点击可切换侧边栏展开/折叠 */}
        <div
          className="sidebar-logo"
          style={{
            flexShrink: 0,
            padding: siderCollapsed ? "16px 0" : "16px 16px",
            textAlign: "center",
            borderBottom: "1px solid var(--ice-border)",
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: siderCollapsed ? "center" : "flex-start",
            gap: 12,
          }}
        >
          <RobotLogo
            collapsed={siderCollapsed}
            onClick={() => isMobile ? setMobileOpen(!mobileOpen) : toggleCollapsed()}
          />
          {!siderCollapsed && (
            <div style={{ textAlign: "left", lineHeight: 1.2 }}>
              <Text strong style={{ fontSize: 17, color: "var(--ice-primary)", letterSpacing: 0.5 }}>AI Agent</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 11 }}>管理平台</Text>
            </div>
          )}
        </div>

        <div className="sidebar-menu-wrap" style={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden" }}>

          <Menu

            mode="inline"

            items={visibleMenuItems}

            selectedKeys={[location.pathname]}

            onClick={({ key }) => navigate(key)}

            style={{ borderRight: "none", background: "transparent", height: "100%" }}

            theme="light"

            className="sidebar-menu"

          />

        </div>

      </Sider>

      <Layout style={{ marginLeft: isMobile ? 0 : undefined }}>

        <Header style={{

          background: "var(--ice-bg-card)", backdropFilter: "blur(20px)",

          borderBottom: "1px solid var(--ice-border)",

          padding: isMobile ? "0 12px" : "0 24px",

          display: "flex", alignItems: "center",

          justifyContent: "space-between", zIndex: 100,

        }}>

          <Space>

            <Button

              type="text"

              icon={isMobile ? <MenuUnfoldOutlined /> : (collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />)}

              onClick={() => isMobile ? setMobileOpen(!mobileOpen) : toggleCollapsed()}

              style={{ color: "var(--ice-text-primary)", fontSize: 16, padding: "4px" }}

            />

          </Space>

          <Space style={{ gap: 12 }}>

            <Button type="text" icon={darkMode ? <SunOutlined /> : <MoonOutlined />}

              onClick={toggleDarkMode} title={darkMode ? "切换到亮色模式" : "切换到深色模式"}

              style={{ color: "var(--ice-text-primary)", fontSize: 16, padding: "4px" }} />

            <Dropdown menu={userMenu} placement="bottomRight" arrow>

              <Space style={{ cursor: "pointer" }}>

                <Avatar icon={<UserOutlined />} style={{ backgroundColor: "var(--ice-primary)", color: "var(--ice-text-inverse)" }} />

                <Text style={{ color: "var(--ice-text-primary)" }}>{user?.username}</Text>

              </Space>

            </Dropdown>

          </Space>

        </Header>

        <Content style={{

          margin: isMobile ? 12 : 24,

          background: "transparent",

          // 固定高度 = 视口高度减去顶栏，使其成为独立的滚动容器：
          // - 内容不超出可视框时，不出现滚动条（overflow: auto 的默认行为）
          // - 内容超出时，自动出现滚动条，顶栏与侧边栏保持固定
          height: `calc(100vh - ${isMobile ? 104 : 64}px)`,

          // 聊天页与画廊页（宽屏，≥861px）自行管理内部滚动（组件内两栏各自 overflow-y: auto），
          // 故保持 hidden；窄屏画廊退化为单栏整页滚动，其余页面由 Content 统一滚动。
          overflow: (isChatPage || (isGalleryPage && winWidth > 860)) ? "hidden" : "auto",

          position: "relative", zIndex: 1,

        }}>

          <Outlet />

        </Content>

      </Layout>

      {isMobile && mobileOpen && (

        <div

          onClick={() => setMobileOpen(false)}

          style={{

            position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",

            zIndex: 999,

          }}

        />

      )}

    </Layout>

  )

}

