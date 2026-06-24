import React, { useEffect, useState } from 'react'
import { Row, Col, Typography } from 'antd'
import { RobotOutlined, BookOutlined, FileTextOutlined, TeamOutlined, SettingOutlined, ArrowUpOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { useAuthStore } from '@/stores/auth'

const { Title, Text } = Typography

export default function Dashboard() {
  const { user } = useAuthStore()
  const [stats, setStats] = useState({ agentCount: 0, kbCount: 0, docCount: 0, userCount: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('/api/agents', { headers: authHeaders() }).then(r => r.json()).catch(() => []),
      fetch('/api/knowledge-bases', { headers: authHeaders() }).then(r => r.json()).catch(() => []),
      fetch('/api/users', { headers: authHeaders() }).then(r => r.json()).catch(() => []),
    ]).then(([agents, kbs, users]) => {
      setStats({
        agentCount: agents.length,
        kbCount: kbs.length,
        docCount: kbs.reduce((sum: number, kb: any) => sum + (kb.document_count || 0), 0),
        userCount: users.length,
      })
      setLoading(false)
    })
  }, [])

  const chartOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category', data: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
      axisLine: { lineStyle: { color: '#556677' } }, axisLabel: { color: '#8899aa' },
    },
    yAxis: {
      type: 'value', axisLine: { show: false },
      splitLine: { lineStyle: { color: 'rgba(0, 212, 255, 0.06)' } }, axisLabel: { color: '#8899aa' },
    },
    series: [{
      name: '对话数', type: 'line', data: [12, 19, 15, 25, 22, 30, 28],
      smooth: true, symbol: 'circle', symbolSize: 6, itemStyle: { color: '#00d4ff' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0, 212, 255, 0.3)' },
          { offset: 1, color: 'rgba(0, 212, 255, 0.02)' },
        ]),
      },
    }],
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ color: '#e8f4f8', margin: 0 }}>欢迎回来, {user?.username} 👋</Title>
        <Text type="secondary">这里是您的管理控制台</Text>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {[
          { label: 'Agent 数量', value: stats.agentCount, icon: <RobotOutlined />, color: '#00d4ff' },
          { label: '知识库数量', value: stats.kbCount, icon: <BookOutlined />, color: '#7b68ee' },
          { label: '文档总数', value: stats.docCount, icon: <FileTextOutlined />, color: '#00ffd5' },
          { label: '用户数量', value: stats.userCount, icon: <TeamOutlined />, color: '#ffb800' },
        ].map((item, i) => (
          <Col span={6} key={item.label}>
            <IceCrystalCard hoverEffect="glow" animation="fadeInUp" style={{ border: `1px solid ${item.color}33`, background: 'rgba(17, 24, 39, 0.85)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 13 }}>{item.label}</Text>
                  <div style={{ fontSize: 28, fontWeight: 700, color: item.color, marginTop: 4 }}>{loading ? '-' : item.value}</div>
                  <Text type="secondary" style={{ fontSize: 12 }}><ArrowUpOutlined style={{ color: '#00ffd5' }} /> 活跃</Text>
                </div>
                <div style={{ fontSize: 32, color: item.color, opacity: 0.6 }}>{item.icon}</div>
              </div>
            </IceCrystalCard>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]}>
        <Col span={16}>
          <IceCrystalCard hoverEffect="none" animation="fadeInUp" title="近 7 天对话趋势" style={{ background: 'rgba(17, 24, 39, 0.85)' }}>
            <ReactECharts option={chartOption} style={{ height: 280 }} />
          </IceCrystalCard>
        </Col>
        <Col span={8}>
          <IceCrystalCard hoverEffect="none" animation="fadeInUp" title="快捷操作" style={{ background: 'rgba(17, 24, 39, 0.85)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { label: '新建 Agent', icon: <RobotOutlined />, path: '/agents' },
                { label: '新建知识库', icon: <BookOutlined />, path: '/knowledge-bases' },
                { label: '用户管理', icon: <TeamOutlined />, path: '/users' },
                { label: '系统设置', icon: <SettingOutlined />, path: '/settings' },
              ].map((item) => (
                <a key={item.label} href={item.path} style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 8,
                  background: 'rgba(0, 212, 255, 0.04)', border: '1px solid rgba(0, 212, 255, 0.08)',
                  color: '#e8f4f8', textDecoration: 'none', transition: 'all 0.2s',
                }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0, 212, 255, 0.1)'; e.currentTarget.style.borderColor = 'rgba(0, 212, 255, 0.25)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(0, 212, 255, 0.04)'; e.currentTarget.style.borderColor = 'rgba(0, 212, 255, 0.08)' }}
                >
                  <span style={{ color: '#00d4ff' }}>{item.icon}</span><span>{item.label}</span>
                </a>
              ))}
            </div>
          </IceCrystalCard>
        </Col>
      </Row>
    </div>
  )
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('agent-token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}
