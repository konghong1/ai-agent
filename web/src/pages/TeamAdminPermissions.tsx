import { useEffect, useMemo, useState } from 'react'
import { Card, Table, Button, Modal, Checkbox, Tag, message, Space, Typography, Input } from 'antd'
import { useAuthStore } from '@/stores/auth'

const { Title, Text } = Typography

// 权限分类中文标签（catalog.category → 展示名）
const CAT_LABELS: Record<string, string> = {
  dashboard: '仪表盘',
  chat: '聊天',
  'knowledge-base': '知识库',
  gallery: '电商套图',
  media: '媒体库',
  memory: '长期记忆',
  mcp: 'MCP',
  skill: 'Skill',
  hook: 'Hook',
  team: '团队',
  admin: '系统管理',
  providers: 'AI 提供商',
  prompt: '提示词模板',
}

interface CatalogItem {
  code: string
  name: string
  category: string
  description: string
  is_system: boolean
  grantable: boolean
}
interface TeamAdmin {
  user_id: number
  email: string
  username: string
  is_team_admin: boolean
  scope: string[]
}
interface AppUser {
  id: number
  email: string
  username: string
  is_superuser: boolean
  is_team_admin: boolean
}

export default function TeamAdminPermissions() {
  const token = useAuthStore((s) => s.token)
  const [catalog, setCatalog] = useState<CatalogItem[]>([])
  const [users, setUsers] = useState<AppUser[]>([])
  const [admins, setAdmins] = useState<TeamAdmin[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<AppUser | null>(null)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')

  const auth = () => ({ Authorization: `Bearer ${token}` })

  const loadAll = async () => {
    setLoading(true)
    try {
      const [c, u, a] = await Promise.all([
        fetch('/api/permissions/catalog', { headers: auth() }).then((r) => r.json()),
        fetch('/api/users', { headers: auth() }).then((r) => r.json()),
        fetch('/api/admin/team-admins', { headers: auth() }).then((r) => r.json()),
      ])
      setCatalog(c.items || [])
      setUsers(u.users || u || [])
      setAdmins(a.team_admins || [])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  const adminScopeMap = useMemo(() => {
    const m: Record<number, string[]> = {}
    admins.forEach((a) => (m[a.user_id] = a.scope))
    return m
  }, [admins])

  const grouped = useMemo(() => {
    const g: Record<string, CatalogItem[]> = {}
    catalog.forEach((c) => {
      if (!g[c.category]) g[c.category] = []
      g[c.category].push(c)
    })
    return g
  }, [catalog])

  const openModal = (u: AppUser) => {
    setEditing(u)
    const scope = adminScopeMap[u.id] || []
    const init: Record<string, boolean> = {}
    catalog.forEach((c) => (init[c.code] = scope.includes(c.code)))
    setChecked(init)
    setModalOpen(true)
  }

  const toggle = (code: string, val: boolean) => setChecked((p) => ({ ...p, [code]: val }))

  const save = async () => {
    if (!editing) return
    const codes = Object.keys(checked).filter((k) => checked[k])
    // 系统级权限不允许授予团队管理员
    const systemCodes = catalog.filter((c) => c.is_system).map((c) => c.code)
    const forbidden = codes.filter((c) => systemCodes.includes(c))
    if (forbidden.length > 0) {
      message.error(`不可授予系统级权限: ${forbidden.join(', ')}`)
      return
    }
    setSaving(true)
    try {
      const res = await fetch('/api/admin/team-admins', {
        method: 'POST',
        headers: { ...auth(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: editing.id, permission_codes: codes }),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        throw new Error(e.detail || `HTTP ${res.status}`)
      }
      message.success(`已保存 ${editing.username} 的授予范围（${codes.length} 项）`)
      setModalOpen(false)
      await loadAll()
    } catch (e: any) {
      message.error(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const removeAdmin = async (u: AppUser) => {
    setSaving(true)
    try {
      const res = await fetch(`/api/admin/team-admins/${u.id}`, { method: 'DELETE', headers: auth() })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      message.success(`已撤销 ${u.username} 的团队管理员身份`)
      await loadAll()
    } catch (e: any) {
      message.error(e.message || '操作失败')
    } finally {
      setSaving(false)
    }
  }

  const filteredUsers = users.filter(
    (u) => !u.is_superuser && (u.username.includes(search) || u.email.includes(search)),
  )

  const columns = [
    { title: '用户名', dataIndex: 'username' },
    { title: '邮箱', dataIndex: 'email' },
    {
      title: '状态',
      key: 'status',
      render: (_: any, u: AppUser) =>
        u.is_team_admin ? <Tag color="gold">团队管理员</Tag> : <Tag>普通用户</Tag>,
    },
    {
      title: '授予范围',
      key: 'scope',
      render: (_: any, u: AppUser) => {
        const s = adminScopeMap[u.id] || []
        if (s.length === 0) return <Text type="secondary">—</Text>
        return (
          <Space wrap size={[4, 4]}>
            {s.slice(0, 6).map((c) => (
              <Tag key={c}>{c}</Tag>
            ))}
            {s.length > 6 && <Tag>+{s.length - 6}</Tag>}
          </Space>
        )
      },
    },
    {
      title: '操作',
      key: 'op',
      render: (_: any, u: AppUser) => (
        <Space>
          <Button type="link" onClick={() => openModal(u)}>
            {u.is_team_admin ? '编辑权限' : '设为团队管理员'}
          </Button>
          {u.is_team_admin && (
            <Button type="link" danger onClick={() => removeAdmin(u)}>
              撤销
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <Title level={3}>团队管理员权限</Title>
      <Text type="secondary">
        超级管理员在此为「团队管理员」分配其可授予的功能范围（scope）。团队管理员仅能在自己 scope 内给成员分配权限；系统级权限（admin.*）不可授予。
      </Text>
      <Card style={{ marginTop: 16 }}>
        <Input.Search
          placeholder="搜索用户名 / 邮箱"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ marginBottom: 12, maxWidth: 320 }}
        />
        <Table
          rowKey="id"
          loading={loading}
          dataSource={filteredUsers}
          columns={columns}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title={editing ? `设置 ${editing.username} 的授予范围` : ''}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={save}
        confirmLoading={saving}
        width={720}
      >
        <Text type="secondary">勾选该团队管理员可授予成员的功能权限：</Text>
        <div style={{ maxHeight: 420, overflowY: 'auto', marginTop: 12 }}>
          {Object.entries(grouped).map(([cat, items]) => (
            <div key={cat} style={{ marginBottom: 16 }}>
              <Title level={5} style={{ marginBottom: 8 }}>
                {CAT_LABELS[cat] || cat}
              </Title>
              <Space wrap size={[8, 8]}>
                {items.map((c) => (
                  <Checkbox
                    key={c.code}
                    checked={!!checked[c.code]}
                    disabled={c.is_system}
                    onChange={(e) => toggle(c.code, e.target.checked)}
                  >
                    {c.name}
                    {c.is_system && <Text type="secondary"> (系统级)</Text>}
                  </Checkbox>
                ))}
              </Space>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  )
}
