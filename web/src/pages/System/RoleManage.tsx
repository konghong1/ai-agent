import { useEffect, useState, useMemo } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined, SafetyCertificateOutlined,
  DashboardOutlined, MessageOutlined, BookOutlined, ShoppingOutlined,
  PictureOutlined, DatabaseOutlined, ApiOutlined, ToolOutlined,
  AppstoreOutlined, SettingOutlined, CloudServerOutlined, FileTextOutlined,
  TeamOutlined, ControlOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Switch, Tag, Popconfirm, Drawer, Spin, message, Tree, Badge, Tooltip } from 'antd'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

interface RoleItem {
  id: number
  code: string
  name: string
  description: string
  is_system: boolean
  is_default: boolean
  sort_order: number
  permissions: string[]
  permission_count: number
}

interface CatalogItem {
  code: string
  name: string
  category: string
  description: string
  is_system: boolean
}

const CATEGORY_LABEL: Record<string, string> = {
  dashboard: '工作台', chat: '聊天', knowledge: '知识库', 'knowledge-base': '知识库',
  gallery: '电商套图', media: '素材库', memory: '长期记忆', mcp: 'MCP', skill: 'Skill', hook: 'Hook',
  providers: 'AI 提供商', prompt: '提示词模板', team: '团队', admin: '系统管理',
}

const CATEGORY_ICON: Record<string, React.ReactNode> = {
  dashboard: <DashboardOutlined />, chat: <MessageOutlined />,
  knowledge: <BookOutlined />, 'knowledge-base': <BookOutlined />,
  gallery: <ShoppingOutlined />, media: <PictureOutlined />,
  memory: <DatabaseOutlined />, mcp: <ApiOutlined />,
  skill: <AppstoreOutlined />, hook: <ToolOutlined />,
  providers: <CloudServerOutlined />, prompt: <FileTextOutlined />,
  team: <TeamOutlined />, admin: <ControlOutlined />,
}

/** 将扁平 catalog 构建为 antd Tree 的 treeData（分类 → 权限码 两级树） */
function buildTreeData(catalog: CatalogItem[]): any[] {
  const catMap = new Map<string, CatalogItem[]>()
  for (const c of catalog) {
    ;(catMap.get(c.category) || []).push(c) || catMap.set(c.category, [c])
  }
  return Array.from(catMap.entries())
    .sort(([a], [b]) => (CATEGORY_LABEL[a] || a).localeCompare(CATEGORY_LABEL[b] || b, 'zh'))
    .map(([cat, items]) => ({
      key: `__cat__${cat}`,
      title: (
        <span>
          {CATEGORY_ICON[cat] || null}
          {' '}{CATEGORY_LABEL[cat] || cat}
          <Badge count={items.length} size="small" style={{ marginLeft: 6 }} />
        </span>
      ),
      children: items
        .sort((a, b) => (a.name).localeCompare(b.name, 'zh'))
        .map((p) => ({
          key: p.code,
          title: (
            <Tooltip title={p.description || undefined} placement="right">
              <span>{p.name}</span>
            </Tooltip>
          ),
          isLeaf: true,
        })),
    }))
}

export default function RoleManage() {
  const [items, setItems] = useState<RoleItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<RoleItem | null>(null)
  const [form] = Form.useForm()

  // 权限分配抽屉
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [permRole, setPermRole] = useState<RoleItem | null>(null)
  const [catalog, setCatalog] = useState<CatalogItem[]>([])
  const [checked, setChecked] = useState<string[]>([])
  const [permLoading, setPermLoading] = useState(false)
  const [savingPerm, setSavingPerm] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/system/roles', { headers: authHeaders() })
      if (r.ok) {
        const data = await r.json()
        setItems(data.items || [])
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ is_default: false })
    setModalOpen(true)
  }

  const openEdit = (r: RoleItem) => {
    setEditing(r)
    form.setFieldsValue({ code: r.code, name: r.name, description: r.description, is_default: r.is_default })
    setModalOpen(true)
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        const res = await fetch(`/api/system/roles/${editing.id}`, {
          method: 'PUT', headers: authHeaders(), body: JSON.stringify(values),
        })
        if (res.ok) { message.success('已更新'); setModalOpen(false); load() }
        else { const e = await res.json(); message.error(e.detail || '更新失败') }
      } else {
        const res = await fetch('/api/system/roles', {
          method: 'POST', headers: authHeaders(), body: JSON.stringify(values),
        })
        if (res.ok) { message.success('已创建'); setModalOpen(false); load() }
        else if (res.status === 409) { message.error('角色 code 已存在') }
        else { const e = await res.json(); message.error(e.detail || '创建失败') }
      }
    } catch (e: any) { if (e?.message) message.error(e.message) }
  }

  const handleDelete = async (r: RoleItem) => {
    const res = await fetch(`/api/system/roles/${r.id}`, { method: 'DELETE', headers: authHeaders() })
    if (res.ok) { message.success('已删除'); load() }
    else { const e = await res.json().catch(() => ({})); message.error(e.detail || '删除失败（系统角色不可删）') }
  }

  const openPermDrawer = async (r: RoleItem) => {
    setPermRole(r)
    setDrawerOpen(true)
    setPermLoading(true)
    try {
      const [catRes, permRes] = await Promise.all([
        fetch('/api/permissions/catalog', { headers: authHeaders() }),
        fetch(`/api/system/roles/${r.id}/permissions`, { headers: authHeaders() }),
      ])
      const cat = await catRes.json()
      const perm = await permRes.json()
      setCatalog(cat.items || [])
      setChecked(perm.permissions || [])
    } finally {
      setPermLoading(false)
    }
  }

  const savePerms = async () => {
    if (!permRole) return
    setSavingPerm(true)
    try {
      const res = await fetch(`/api/system/roles/${permRole.id}/permissions`, {
        method: 'PUT', headers: authHeaders(), body: JSON.stringify({ codes: checked }),
      })
      if (res.ok) { message.success('权限已保存'); setDrawerOpen(false); load() }
      else { const e = await res.json(); message.error(e.detail || '保存失败') }
    } finally {
      setSavingPerm(false)
    }
  }

  // 树状权限数据（从 catalog 构建，分类→权限码 两级）
  const treeData = useMemo(() => buildTreeData(catalog), [catalog])
  // Tree 展开状态：默认全部展开
  const expandedKeys = useMemo(() => treeData.map(n => n.key), [treeData])

  // 按 category 分组目录（保留用于统计等）
  const grouped = catalog.reduce<Record<string, CatalogItem[]>>((acc, c) => {
    ;(acc[c.category] ||= []).push(c)
    return acc
  }, {})

  const columns = [
    { title: 'Code', dataIndex: 'code', key: 'code', width: 160, render: (t: string) => <Text code style={{ color: 'var(--ice-text-primary)' }}>{t}</Text> },
    { title: '名称', dataIndex: 'name', key: 'name', width: 160 },
    { title: '描述', dataIndex: 'description', key: 'description', render: (t: string) => t || <Text type="secondary">—</Text> },
    { title: '默认角色', dataIndex: 'is_default', key: 'is_default', width: 100, render: (v: boolean) => v ? <Tag color="green">默认</Tag> : <Tag>否</Tag> },
    { title: '系统', dataIndex: 'is_system', key: 'is_system', width: 90, render: (v: boolean) => v ? <Tag color="gold">系统</Tag> : <Tag>自定义</Tag> },
    { title: '权限数', dataIndex: 'permission_count', key: 'permission_count', width: 80 },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: any, r: RoleItem) => (
        <Space>
          <a onClick={() => openPermDrawer(r)} title="分配权限"><SafetyCertificateOutlined /></a>
          <a onClick={() => openEdit(r)}><EditOutlined /></a>
          <Popconfirm title="确认删除该角色?" disabled={r.is_system} onConfirm={() => handleDelete(r)} okText="删除" okButtonProps={{ danger: true }}>
            <a style={{ color: r.is_system ? 'var(--ice-text-disabled)' : 'var(--ice-danger)' }} onClick={(e) => { if (r.is_system) e.preventDefault() }}><DeleteOutlined /></a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>角色管理（显式 RBAC）</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增角色</Button>
      </div>
      <Text type="secondary">角色为全局角色（不按团队细分）。标记为「默认角色」后，新注册用户及既有用户将自动获得。权限判定为「角色权限 ∪ 个人授权」加性并集。</Text>
      <Table columns={columns} dataSource={items} rowKey="id" loading={loading} pagination={false} style={{ marginTop: 12 }} />

      <Modal
        title={editing ? '编辑角色' : '新增角色'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        okText="保存"
        cancelText="取消"
        width={480}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="code" label="角色 Code" rules={[{ required: true, message: '必填' }]}>
            <Input disabled={!!editing} placeholder="如 editor / auditor" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="角色显示名" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
          <Form.Item name="is_default" label="设为默认角色（新用户自动获得）" valuePropName="checked" tooltip="开启后所有用户将自动获得该角色">
            <Switch disabled={editing?.is_system} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={permRole ? `分配权限 — ${permRole.name}` : '分配权限'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={560}
        footer={<Space style={{ float: 'right' }}>
          <Button onClick={() => setDrawerOpen(false)}>取消</Button>
          <Button type="primary" loading={savingPerm} onClick={savePerms}>保存权限</Button>
        </Space>}
      >
        {permLoading ? <Spin /> : (
          <div style={{ maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', paddingRight: 4 }}>
            <Tree
              checkable
              treeData={treeData}
              defaultExpandAll
              checkedKeys={checked}
              onCheck={(checkedKeys) => {
                // antd Tree 的 checkedKeys 包含父节点 key（__cat__xxx），只取叶子节点（权限码）
                const keys = Array.isArray(checkedKeys) ? checkedKeys : (checkedKeys as any).checked || []
                setChecked(keys.filter((k: string) => !k.startsWith('__cat__')))
              }}
              style={{ background: 'transparent' }}
            />
          </div>
        )}
      </Drawer>
    </IceCrystalCard>
  )
}
