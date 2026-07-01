import { useEffect, useState } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Switch, Tag, message } from 'antd'
import { useLayoutStore } from '@/stores/layout'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

export default function MCPManagement() {
  const theme = useLayoutStore((s) => s.theme)
  const [items, setItems] = useState<any[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()

  const themeColorMap: Record<string, string> = {
    techBlue: '#2563EB',
    naturalGreen: '#22C55E',
    elegantPurple: '#7C3AED',
  }
  const primaryColor = themeColorMap[theme] || '#22C55E'

  const fetchItems = async () => {
    try {
      const r = await fetch('/api/mcp-servers', { headers: authHeaders() })
      if (r.ok) {
        const data = await r.json()
        setItems(Array.isArray(data) ? data : [])
      }
    } catch { /* silent */ }
  }
  useEffect(() => { fetchItems() }, [])

  const handleSave = async (values: any) => {
    try {
      const url = editing ? `/api/mcp-servers/${editing.id}` : '/api/mcp-servers'
      const res = await fetch(url, { method: editing ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(values) })
      if (res.ok) { message.success('保存成功'); setModalOpen(false); fetchItems() }
    } catch (e: any) { message.error(e.message) }
  }

  const handleDelete = (id: number) => {
    fetch(`/api/mcp-servers/${id}`, { method: 'DELETE', headers: authHeaders() }).then(() => fetchItems())
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', render: (t: string) => <Text style={{ color: 'var(--ice-text-primary)', fontWeight: 600 }}>{t}</Text> },
    { title: '传输方式', dataIndex: 'transport', key: 'transport', width: 100, render: (t: string) => <Tag color="cyan">{t}</Tag> },
    { title: '命令/URL', dataIndex: editing ? 'command' : 'url', key: 'cmd', ellipsis: true,
      render: (_: any, r: any) => <Text type="secondary" style={{ fontSize: 12 }}>{r.transport === 'http' ? r.url : r.command}</Text> },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80,
      render: (e: boolean, r: any) => <Switch checked={e} onChange={(v) => { fetch(`/api/mcp-servers/${r.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ enabled: v }) })}} size="small" /> },
    { title: '操作', key: 'action', width: 100,
      render: (_: any, r: any) => (
        <Space>
          <a onClick={() => { setEditing(r); form.setFieldsValue(r); setModalOpen(true) }}><EditOutlined /></a>
          <a onClick={() => handleDelete(r.id)} style={{ color: 'var(--ice-danger)' }}><DeleteOutlined /></a>
        </Space>
      )}]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>MCP Server 管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.setFieldsValue({ transport: 'stdio', enabled: true }); form.resetFields(); setModalOpen(true) }}>添加 MCP</Button>
      </div>
      <Table columns={columns} dataSource={items} rowKey="id" pagination={false} />

      <Modal title={editing ? '编辑 MCP Server' : '新建 MCP Server'} open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} width={520}>
        <Form form={form} layout="vertical" onFinish={handleSave} initialValues={{ transport: 'stdio', enabled: true }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="transport" label="传输方式" rules={[{ required: true }]}>
            <Select options={[{ value: 'stdio', label: 'stdio' }, { value: 'http', label: 'http' }]} />
          </Form.Item>
          <Form.Item name="command" label="命令" dependencies={['transport']}
            rules={(getFieldValue: any) => getFieldValue('transport') === 'stdio' ? [{ required: true }] : []}>
            <Input placeholder="npx" />
          </Form.Item>
          <Form.Item name="args" label="参数">
            <Input placeholder="逗号分隔的参数" />
          </Form.Item>
          <Form.Item name="url" label="URL" dependencies={['transport']}
            rules={(getFieldValue: any) => getFieldValue('transport') === 'http' ? [{ required: true }] : []}>
            <Input placeholder="https://api.example.com/mcp" />
          </Form.Item>
          <Form.Item name="enabled" valuePropName="checked" label="启用"><Switch /></Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" style={{ marginRight: 8 }}>确定</Button>
            <Button onClick={() => setModalOpen(false)}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}
