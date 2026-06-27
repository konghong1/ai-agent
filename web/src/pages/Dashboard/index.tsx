import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Row, Col, Typography } from 'antd'
import { RobotOutlined, BookOutlined, FileTextOutlined, TeamOutlined, SettingOutlined, ArrowUpOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { useAuthStore } from '@/stores/auth'
import { useLayoutStore } from '@/stores/layout'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

export default function Dashboard() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const theme = useLayoutStore((s) => s.theme)
  const [stats, setStats] = useState({ agentCount: 0, kbCount: 0, docCount: 0, userCount: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('/api/agents', { headers: authHeaders() }).then(r => r.json()).catch(() => []),
      fetch('/api/knowledge-bases', { headers: authHeaders() }).then(r => r.json()).catch(() => []),
      fetch('/api/users', { headers: authHeaders() }).then(r => r.json()).catch(() => [])]).then(([agents, kbs, users]) => {
      setStats({
        agentCount: agents.length,
        kbCount: kbs.length,
        docCount: kbs.reduce((sum: number, kb: any) => sum + (kb.document_count || 0), 0),
        userCount: users.length})
      setLoading(false)
    })
  }, [])

  const themeColorMap: Record<string, string> = {
    techBlue: '#2563EB',
    naturalGreen: '#22C55E',
    elegantPurple: '#7C3AED',
  }
  const primaryColor = themeColorMap[theme] || '#22C55E'
  const accentColor = theme === 'techBlue' ? '#60A5FA' : theme === 'naturalGreen' ? '#86EFAC' : '#A78BFA'

  const chartOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category', data: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
      axisLine: { lineStyle: { color: 'var(--ice-text-muted)' } }, axisLabel: { color: 'var(--ice-text-secondary)' }},
    yAxis: {
      type: 'value', axisLine: { show: false },
      splitLine: { lineStyle: { color: primaryColor + '10' } }, axisLabel: { color: 'var(--ice-text-secondary)' }},
    series: [{
      name: '对话数', type: 'line', data: [12, 19, 15, 25, 22, 30, 28],
      smooth: true, symbol: 'circle', symbolSize: 6, itemStyle: { color: primaryColor },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: primaryColor + '4D' },
          { offset: 1, color: primaryColor + '05' }])}}]}

  const statItems = [
    { label: 'Agent 数量', value: stats.agentCount, icon: <RobotOutlined />, color: primaryColor },
    { label: '知识库数量', value: stats.kbCount, icon: <BookOutlined />, color: 'var(--ice-secondary)' },
    { label: '文档总数', value: stats.docCount, icon: <FileTextOutlined />, color: accentColor },
    { label: '用户数量', value: stats.userCount, icon: <TeamOutlined />, color: 'var(--ice-warning)' }
  ]

  const quickActions = [
    { label: '新建 Agent', icon: <RobotOutlined />, path: '/agents' },
    { label: '新建知识库', icon: <BookOutlined />, path: '/knowledge-bases' },
    { label: '用户管理', icon: <TeamOutlined />, path: '/users' },
    { label: '系统设置', icon: <SettingOutlined />, path: '/settings' }
  ]

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>欢迎回来, {user?.username} 👋</Title>
        <Text type="secondary">这里是您的管理控制台</Text>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {statItems.map((item) => (
          <Col span={6} key={item.label}>
            <IceCrystalCard hoverEffect="glow" animation="fadeInUp" style={{ borderColor: typeof item.color === 'string' && item.color.startsWith('#') ? item.color + '33' : 'var(--ice-border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 13 }}>{item.label}</Text>
                  <div style={{ fontSize: 28, fontWeight: 700, color: typeof item.color === 'string' && item.color.startsWith('#') ? item.color : 'var(--ice-text-primary)', marginTop: 4 }}>{loading ? '-' : item.value}</div>
                  <Text type="secondary" style={{ fontSize: 12 }}><ArrowUpOutlined style={{ color: accentColor }} /> 活跃</Text>
                </div>
                <div style={{ fontSize: 32, color: typeof item.color === 'string' && item.color.startsWith('#') ? item.color : 'var(--ice-text-primary)', opacity: 0.6 }}>{item.icon}</div>
              </div>
            </IceCrystalCard>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]}>
        <Col span={16}>
          <IceCrystalCard hoverEffect="none" animation="fadeInUp" title="近 7 天对话趋势">
            <ReactECharts option={chartOption} style={{ height: 280 }} />
          </IceCrystalCard>
        </Col>
        <Col span={8}>
          <IceCrystalCard hoverEffect="none" animation="fadeInUp" title="快捷操作">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {quickActions.map((item) => (
                <a key={item.label} onClick={(e) => { e.preventDefault(); navigate(item.path) }} style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 8,
                  background: 'var(--ice-bg-hover)', border: '1px solid var(--ice-border)',
                  color: 'var(--ice-text-primary)', textDecoration: 'none', transition: 'all 0.2s'}}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--ice-primary-10)'; e.currentTarget.style.borderColor = 'var(--ice-primary)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--ice-bg-hover)'; e.currentTarget.style.borderColor = 'var(--ice-border)' }}
                >
                  <span style={{ color: primaryColor }}>{item.icon}</span><span>{item.label}</span>
                </a>
              ))}
            </div>
          </IceCrystalCard>
        </Col>
      </Row>
    </div>
  )
}

