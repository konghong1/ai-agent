import React from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Button, Space, Typography } from 'antd'
import {
  DashboardOutlined, RobotOutlined, BookOutlined, TeamOutlined,
  LinkOutlined, ThunderboltOutlined, SettingOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined, LogoutOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '@/stores/auth'
import { useLayoutStore } from '@/stores/layout'
import { ParticleBg } from '@/components/ParticleBg'

const { Sider, Header, Content } = Layout
const { Text } = Typography

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/agents', icon: <RobotOutlined />, label: 'Agent 目录' },
  { key: '/knowledge-bases', icon: <BookOutlined />, label: '知识库' },
  { key: '/users', icon: <TeamOutlined />, label: '用户管理' },
  { key: '/mcp-servers', icon: <LinkOutlined />, label: 'MCP 管理' },
  { key: '/skills', icon: <ThunderboltOutlined />, label: 'Skill 管理' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
]

export default function BasicLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { collapsed, toggleCollapsed } = useLayoutStore()
  const { user, logout } = useAuthStore()

  const userMenu = {
    items: [
      { key: 'username', label: <Text style={{ color: '#e8f4f8' }}>{user?.username}</Text>, disabled: true },
      { type: 'divider' as const },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录',
        onClick: () => { logout(); navigate('/login') } },
    ],
  }

  return (
    <Layout className="main-layout" style={{ minHeight: '100vh' }}>
      <ParticleBg count={25} speed={0.2} opacity={0.2} />
      <Sider
        collapsible collapsed={collapsed} onCollapse={toggleCollapsed} width={256}
        style={{
          background: 'rgba(17, 25, 47, 0.92)',
          borderRight: '1px solid rgba(0, 212, 255, 0.12)',
          zIndex: 10,
        }}
      >
        <div style={{ padding: '24px 16px', textAlign: 'center', borderBottom: '1px solid rgba(0, 212, 255, 0.08)' }}>
          <Text strong style={{ fontSize: 20, color: '#00d4ff', letterSpacing: 1 }}>AI Agent</Text>
          <br /><Text type="secondary" style={{ fontSize: 12 }}>管理平台</Text>
        </div>
        <Menu
          mode="inline"
          items={menuItems}
          selectedKeys={[location.pathname]}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 'none', background: 'transparent' }}
          theme="light"
          className="sidebar-menu"
        />
      </Sider>
      <Layout>
        <Header style={{
          background: 'rgba(17, 25, 47, 0.85)', backdropFilter: 'blur(20px)',
          borderBottom: '1px solid rgba(0, 212, 255, 0.12)',
          padding: '0 24px', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', zIndex: 10,
        }}>
          <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggleCollapsed} style={{ color: '#e8f4f8', fontSize: 16, padding: '4px' }} />
          <Dropdown menu={userMenu} placement="bottomRight" arrow>
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#00d4ff', color: '#0a0e17' }} />
              <Text style={{ color: '#e8f4f8' }}>{user?.username}</Text>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{
          margin: 24, background: 'transparent', minHeight: 'calc(100vh - 64px)',
          overflow: 'auto', position: 'relative', zIndex: 1,
        }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
