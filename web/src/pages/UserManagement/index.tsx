import { useEffect, useState } from 'react'
import { EditOutlined, DeleteOutlined, UserSwitchOutlined } from '@ant-design/icons'
import { Navigate } from 'react-router-dom'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Switch, Tag, Drawer, Divider, message } from 'antd'
import { authHeaders } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'

const { Title, Text } = Typography

interface User {
  id: number; email: string; username: string; role: string; is_superuser: boolean; enabled: boolean; created_at: string
}

export default function UserManagement() {
  const { user } = useAuthStore()
  if (!user?.is_superuser) return <Navigate to="/dashboard" replace />
  const [users, setUsers] = useState<User[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [form] = Form.useForm()

  // 分配角色抽屉
  const [roleDrawer, setRoleDrawer] = useState(false)
  const [targetUser, setTargetUser] = useState<User | null>(null)
  const [userRoles, setUserRoles] = useState<{ role_id: number; role_name: string; role_code: string; is_system: boolean }[]>([])
  const [allRoles, setAllRoles] = useState<{ id: number; name: string; code: string }[]>([])
  const [roleSaving, setRoleSaving] = useState(false)

  const openRoleDrawer = async (u: User) => {
    setTargetUser(u)
    setRoleDrawer(true)
    try {
      const [urRes, rRes] = await Promise.all([
        fetch(`/api/users/${u.id}/roles`, { headers: authHeaders() }),
        fetch('/api/system/roles', { headers: authHeaders() }),
      ])
      const ur = await urRes.json()
      const r = await rRes.json()
      setUserRoles(ur.roles || [])
      setAllRoles((r.items || []).map((x: any) => ({ id: x.id, name: x.name, code: x.code })))
    } catch {}
  }

  const assignRole = async (roleId: number) => {
    if (!targetUser) return
    setRoleSaving(true)
    try {
      const res = await fetch(`/api/users/${targetUser.id}/roles`, {
        method: 'POST', headers: authHeaders(), body: JSON.stringify({ role_id: roleId, team_id: null }),
      })
      if (res.ok) {
        message.success('已分配角色')
        const rRes = await (await fetch('/api/users/' + targetUser.id + '/roles', { headers: authHeaders() })).json()
        setUserRoles(rRes.roles || [])
      } else if (res.status === 409) { message.warning('用户已拥有该角色') }
      else { const e = await res.json().catch(() => ({})); message.error(e.detail || '分配失败') }
    } finally { setRoleSaving(false) }
  }

  const unassignRole = async (roleId: number) => {
    if (!targetUser) return
    const res = await fetch(`/api/users/${targetUser.id}/roles/${roleId}`, { method: 'DELETE', headers: authHeaders() })
    if (res.ok) {
      message.success('已撤销角色')
      const rRes = await (await fetch('/api/users/' + targetUser.id + '/roles', { headers: authHeaders() })).json()
      setUserRoles(rRes.roles || [])
    } else { const e = await res.json().catch(() => ({})); message.error(e.detail || '撤销失败') }
  }

  const fetchUsers = async () => {
    try {
      const r = await fetch('/api/users', { headers: authHeaders() })
      if (r.ok) {
        const data = await r.json()
        setUsers(Array.isArray(data) ? data : [])
      }
    } catch {}
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
    { title: '超级管理员', dataIndex: 'is_superuser', key: 'is_superuser', width: 100,
      render: (v: boolean) => <Tag color={v ? 'gold' : 'default'}>{v ? '超级管理员' : '否'}</Tag> },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80,
      render: (e: boolean, u: User) => <Switch checked={e} onChange={(v) => handleToggle(u, v)} size="small" /> },
    { title: '操作', key: 'action', width: 150,
      render: (_: any, u: User) => (
        <Space>
          <a onClick={() => openRoleDrawer(u)} title="分配角色"><UserSwitchOutlined /></a>
          <a onClick={() => { setEditing(u); form.setFieldsValue(u); setModalOpen(true) }}><EditOutlined /></a>
          <a onClick={() => handleDelete(u)} style={{ color: 'var(--ice-danger)' }}><DeleteOutlined /></a>
        </Space>
      )}]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>用户管理（通过注册接口创建新用户）</Title>
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
          <Form.Item name="is_superuser" valuePropName="checked" label="超级管理员"><Switch /></Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" style={{ marginRight: 8 }}>确定</Button>
            <Button onClick={() => setModalOpen(false)}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={targetUser ? `分配角色 — ${targetUser.username}` : '分配角色'}
        open={roleDrawer}
        onClose={() => setRoleDrawer(false)}
        width={460}
      >
        <Text strong style={{ color: 'var(--ice-text-primary)' }}>当前角色</Text>
        <div style={{ margin: '12px 0' }}>
          {userRoles.length === 0 ? <Text type="secondary">暂无角色（仅有个人空间默认权限）</Text> : (
            <Space wrap>
              {userRoles.map((r) => (
                <Tag key={r.role_id} color={r.is_system ? 'gold' : 'blue'} closable onClose={() => unassignRole(r.role_id)}>
                  {r.role_name}（{r.role_code}）
                </Tag>
              ))}
            </Space>
          )}
        </div>
        <Divider />
        <Text strong style={{ color: 'var(--ice-text-primary)' }}>分配新角色</Text>
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <Select
            style={{ flex: 1 }}
            showSearch
            optionFilterProp="label"
            placeholder="选择角色"
            options={allRoles.filter((r) => !userRoles.some((ur) => ur.role_id === r.id)).map((r) => ({ value: r.id, label: `${r.name}（${r.code}）` }))}
            onChange={(v) => assignRole(Number(v))}
            disabled={roleSaving}
            notFoundContent="无可分配角色"
          />
        </div>
        <Text type="secondary" style={{ display: 'block', marginTop: 12 }}>角色为全局角色，不按团队细分。分配后该用户即获得角色所包含的权限（加性并入个人授权）。</Text>
      </Drawer>
    </IceCrystalCard>
  )
}

