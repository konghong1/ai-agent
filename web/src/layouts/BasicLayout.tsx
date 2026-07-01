import { useEffect, useState } from "react"

import { Outlet, useNavigate, useLocation } from "react-router-dom"

import { Layout, Menu, Avatar, Button, Space, Typography, Dropdown } from "antd"

import {

  DashboardOutlined, RobotOutlined, TeamOutlined,

  SettingOutlined,

  MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined, LogoutOutlined,

  SunOutlined, MoonOutlined, CloudServerOutlined,

} from "@ant-design/icons"

import { useAuthStore } from "@/stores/auth"

import { useLayoutStore } from "@/stores/layout"

import { ParticleBg } from "@/components/ParticleBg"



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

      { key: "/prompt-templates", label: "提示词模板" },

    ],

  },

  {

    key: "/resources",

    icon: <CloudServerOutlined />,

    label: "资源中心",

    children: [

      { key: "/knowledge-bases", label: "知识库" },

    ],

  },

  { key: "/users", icon: <TeamOutlined />, label: "用户管理" },

  { key: "/settings", icon: <SettingOutlined />, label: "系统设置" },

]



export default function BasicLayout() {

  const navigate = useNavigate()

  const location = useLocation()

  const isChatPage = location.pathname === "/agents/chat"

  const { collapsed, toggleCollapsed } = useLayoutStore()

  const { darkMode, toggleDarkMode } = useLayoutStore()

  const { user, logout } = useAuthStore()

  const [mobileOpen, setMobileOpen] = useState(false)



  useEffect(() => {

    setMobileOpen(false)

  }, [location.pathname])



  useEffect(() => {

    const handleResize = () => {

      if (window.innerWidth < 768) {

        setMobileOpen(false)

      }

    }

    window.addEventListener("resize", handleResize)

    return () => window.removeEventListener("resize", handleResize)

  }, [])



  const isMobile = typeof window !== "undefined" && window.innerWidth < 768



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

        collapsible={isMobile ? false : true}

        collapsed={isMobile ? mobileOpen : collapsed}

        onCollapse={isMobile ? setMobileOpen : toggleCollapsed}

        width={256}

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

        <div style={{ padding: "20px 16px", textAlign: "center", borderBottom: "1px solid var(--ice-border)" }}>

          <Text strong style={{ fontSize: 18, color: "var(--ice-primary)", letterSpacing: 1 }}>AI Agent</Text>

          <br /><Text type="secondary" style={{ fontSize: 12 }}>管理平台</Text>

        </div>

        <Menu

          mode="inline"

          items={menuItems}

          selectedKeys={[location.pathname]}

          onClick={({ key }) => navigate(key)}

          style={{ borderRight: "none", background: "transparent" }}

          theme="light"

          className="sidebar-menu"

        />

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

          minHeight: `calc(100vh - ${isMobile ? 104 : 64}px)`,

          height: isChatPage ? `calc(100vh - ${isMobile ? 104 : 64}px)` : undefined,

          overflow: "hidden", position: "relative", zIndex: 1,

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

