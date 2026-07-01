import { useCallback, useEffect, useState } from 'react'
import { Table, Tag, Switch, Button, Space, Modal, Form, Input, Slider, message, Typography, Tooltip } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { useLayoutStore } from '@/stores/layout'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

interface Agent {
  id: number; name: string; description: string; system_prompt: string
  model_provider: string; model_name: string; temperature: number; enabled: boolean; created_at: string; updated_at: string
}

export default function AgentList() {
  const navigate = useNavigate()
  const theme = useLayoutStore((s) => s.theme)
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null)
  const [form] = Form.useForm()

  const themeColorMap: Record<string, string> = {
    techBlue: '#2563EB',
    naturalGreen: '#22C55E',
    elegantPurple: '#7C3AED',
  }
  const primaryColor = themeColorMap[theme] || '#22C55E'

  const fetchAgents = useCallback(async () => {
    try { const res = await fetch("/api/agents", { headers: authHeaders() }); if (!res.ok) { setAgents([]); return }; setAgents(await res.json()) } catch {}
  }, [])

  useEffect(() => { fetchAgents() }, [fetchAgents])

  const handleSave = async (values: any) => {
    setLoading(true)
    try {
      const url = editingAgent ? '/api/agents/' + editingAgent.id : '/api/agents'
      const method = editingAgent ? 'PATCH' : 'POST'
      const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(values) })
      if (!res.ok) throw new Error('保存失败')
      message.success(editingAgent ? '更新成功' : '创建成功')
      setDrawerOpen(false); setEditingAgent(null); form.resetFields(); fetchAgents()
    } catch (e: any) { message.error(e.message) }
    finally { setLoading(false) }
  }

  const handleDelete = (id: number) => {
    Modal.confirm({ title: '确认删除', content: '删除后无法恢复', okText: '删除', okType: 'danger',
      onOk: async () => { const r = await fetch('/api/agents/' + id, { method: 'DELETE', headers: authHeaders() }); if (r.ok) { message.success('已删除'); fetchAgents() } } })
  }

  const handleToggle = async (id: number, checked: boolean) => {
    await fetch('/api/agents/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ enabled: checked }) })
    fetchAgents()
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 160,
      render: (name: string, r: Agent) => <a onClick={() => navigate('/agents/' + r.id)} style={{ color: primaryColor }}>{name}</a> },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true,
      render: (d: string) => d && d.length > 40 ? <Tooltip title={d}>{d.slice(0, 40)}...</Tooltip> : d },
    { title: '模型', dataIndex: 'model_name', key: 'model_name', width: 120, render: (m: string) => <Tag color="cyan">{m}</Tag> },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80, render: (e: boolean, r: Agent) => <Switch checked={e} onChange={(v) => handleToggle(r.id, v)} size="small" /> },
    { title: '操作', key: 'action', width: 140, fixed: 'right' as const,
      render: (_: any, r: Agent) => (
        <Space>
          <a onClick={() => navigate('/agents/' + r.id)}><EyeOutlined /></a>
          <a onClick={() => { setEditingAgent(r); form.setFieldsValue(r); setDrawerOpen(true) }}><EditOutlined /></a>
          <a onClick={() => handleDelete(r.id)} style={{ color: 'var(--ice-danger)' }}><DeleteOutlined /></a>
        </Space>
      )}]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>Agent 目录</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingAgent(null); form.setFieldsValue({ temperature: 0.7, enabled: true }); form.resetFields(); setDrawerOpen(true) }}>新建 Agent</Button>
      </div>
      <Table columns={columns} dataSource={agents} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} scroll={{ x: 800 }} />

      <Modal title={editingAgent ? '编辑 Agent' : '新建 Agent'} open={drawerOpen} onCancel={() => setDrawerOpen(false)} footer={null} width={600}>
        <Form form={form} layout="vertical" onFinish={handleSave} initialValues={{ temperature: 0.7, enabled: true }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}><Input placeholder="例如: 代码助手" /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea placeholder="简短描述" /></Form.Item>
          <Form.Item name="system_prompt" label="系统提示词"><Input.TextArea rows={4} placeholder="Agent 的系统指令.." /></Form.Item>
          <Form.Item name="model_name" label="模型名称"><Input placeholder="例如: gpt-4o-mini" /></Form.Item>
          <Form.Item name="temperature" label="温度" rules={[{ type: 'number', min: 0, max: 2 }]}>
            <Slider min={0} max={2} step={0.1} marks={{ 0: '0', 1: '1', 2: '2' }} />
          </Form.Item>
          <Form.Item name="enabled" valuePropName="checked" label="启用"><Switch /></Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={loading} style={{ marginRight: 8 }}>确定</Button>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}
