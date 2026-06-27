import { useEffect, useState } from 'react'
import { EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Switch, message } from 'antd'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

interface User {
  id: number; email: string; username: string; role: string; enabled: boolean; created_at: string
}

export default function UserManagement() {
  const [users, setUsers] = useState<User[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [form] = Form.useForm()

  const fetchUsers = async () => {
    try { const r = await fetch('/api/users', { headers: authHeaders() }); setUsers(await r.json()) } catch {}
  }

  useEffect(() => { fetchUsers() }, [])

  const handleSave = async (values: any) => {
    try {
      const res = await fetch(`/api/users/${editing!.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(values)})
      if (res.ok) { message.success('更新成功'); setModalOpen(false); fetchUsers() }
    } catch (e: any) { message.error(e.message) }
  }

  const handleToggle = async (u: User, checked: boolean) => {
    await fetch(`/api/users/${u.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ enabled: checked })})
    fetchUsers()
  }

  const handleDelete = (u: User) => {
    Modal.confirm({
      title: '确认删除', content: `确定删除用户 ${u.username}?`,
      okText: '删除', okType: 'danger',
      onOk: async () => {
        const r = await fetch(`/api/users/${u.id}`, { method: 'DELETE', headers: authHeaders() })
        if (r.ok) { message.success('已删除'); fetchUsers() }
      }})
  }

  const roleColor: Record<string, string> = { admin: 'green', editor: 'blue', user: 'orange' }

  const columns = [
    { title: '用户名', dataIndex: 'username', key: 'username', render: (t: string) => <Text strong style={{ color: 'var(--ice-text-primary)' }}>{t}</Text> },
    { title: '邮箱', dataIndex: 'email', key: 'email', render: (t: string) => <Text style={{ color: 'var(--ice-text-secondary)' }}>{t}</Text> },
    { title: '角色', dataIndex: 'role', key: 'role', width: 100,
      render: (r: string) => <Tag color={roleColor[r] || 'default'}>{r}</Tag> },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80,
      render: (e: boolean, u: User) => <Switch checked={e} onChange={(v) => handleToggle(u, v)} size="small" /> },
    { title: '操作', key: 'action', width: 120,
      render: (_: any, u: User) => (
        <Space>
          <a onClick={() => { setEditing(u); form.setFieldsValue(u); setModalOpen(true) }}><EditOutlined /></a>
          <a onClick={() => handleDelete(u)} style={{ color: 'var(--ice-danger)' }}><DeleteOutlined /></a>
        </Space>
      )}]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>用户管理</Title>
      </div>
      <Table columns={columns} dataSource={users} rowKey="id" pagination={false} />

      <Modal title="编辑用户" open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} width={480}>
        <Form form={form} layout="vertical" onFinish={handleSave} initialValues={{ role: 'user' }}>
          <Form.Item name="username" label="用户名"><Input disabled /></Form.Item>
          <Form.Item name="email" label="邮箱"><Input disabled /></Form.Item>
          <Form.Item name="role" label="角色">
            <Select options={[{ value: 'admin', label: '管理员' }, { value: 'editor', label: '编辑' }, { value: 'user', label: '用户' }]} />
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
