import { useEffect, useState } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Switch, Tag, InputNumber, Popconfirm, message } from 'antd'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

interface ResourceItem {
  id: number
  code: string
  name: string
  type: string
  category: string
  parent_code: string | null
  path: string | null
  icon: string | null
  sort_order: number
  permission_code: string | null
  is_visible: boolean
  is_system: boolean
}

const TYPE_OPTIONS = [
  { value: 'menu', label: '菜单' },
  { value: 'permission', label: '权限码' },
  { value: 'api', label: 'API' },
]

const TYPE_COLOR: Record<string, string> = { menu: 'blue', permission: 'purple', api: 'cyan' }

export default function ResourceManage() {
  const [items, setItems] = useState<ResourceItem[]>([])
  const [menuOptions, setMenuOptions] = useState<{ value: string; label: string }[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ResourceItem | null>(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/system/resources', { headers: authHeaders() })
      if (r.ok) {
        const data = await r.json()
        const list: ResourceItem[] = data.items || []
        setItems(list)
        setMenuOptions(
          list.filter((i) => i.type === 'menu').map((i) => ({ value: i.code, label: `${i.name} (${i.code})` }))
        )
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ type: 'menu', is_visible: true, sort_order: 0 })
    setModalOpen(true)
  }

  const openEdit = (r: ResourceItem) => {
    setEditing(r)
    form.setFieldsValue({
      code: r.code, name: r.name, type: r.type, category: r.category,
      parent_code: r.parent_code, path: r.path, component: r.component, icon: r.icon,
      sort_order: r.sort_order, permission_code: r.permission_code, is_visible: r.is_visible,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    try {
      const body = { ...values }
      if (editing) {
        // code 不可改
        delete body.code
        const res = await fetch(`/api/system/resources/${editing.code}`, {
          method: 'PUT', headers: authHeaders(), body: JSON.stringify(body),
        })
        if (res.ok) { message.success('已更新'); setModalOpen(false); load() }
        else { const e = await res.json(); message.error(e.detail || '更新失败') }
      } else {
        const res = await fetch('/api/system/resources', {
          method: 'POST', headers: authHeaders(), body: JSON.stringify(body),
        })
        if (res.ok) { message.success('已创建'); setModalOpen(false); load() }
        else if (res.status === 409) { message.error('资源 code 已存在') }
        else { const e = await res.json(); message.error(e.detail || '创建失败') }
      }
    } catch (e: any) { if (e?.message) message.error(e.message) }
  }

  const handleDelete = async (r: ResourceItem) => {
    const res = await fetch(`/api/system/resources/${r.code}`, { method: 'DELETE', headers: authHeaders() })
    if (res.ok) { message.success('已删除'); load() }
    else { const e = await res.json().catch(() => ({})); message.error(e.detail || '删除失败（系统资源或有子项不可删）') }
  }

  const columns = [
    { title: 'Code', dataIndex: 'code', key: 'code', width: 200, render: (t: string) => <Text code style={{ color: 'var(--ice-text-primary)' }}>{t}</Text> },
    { title: '名称', dataIndex: 'name', key: 'name', width: 140 },
    { title: '类型', dataIndex: 'type', key: 'type', width: 90, render: (t: string) => <Tag color={TYPE_COLOR[t] || 'default'}>{TYPE_OPTIONS.find((o) => o.value === t)?.label || t}</Tag> },
    { title: '父级', dataIndex: 'parent_code', key: 'parent_code', width: 160, render: (t: string | null) => t ? <Text type="secondary">{t}</Text> : <Text type="secondary">—</Text> },
    { title: '路由', dataIndex: 'path', key: 'path', width: 140, render: (t: string | null) => t || <Text type="secondary">—</Text> },
    { title: '权限码', dataIndex: 'permission_code', key: 'permission_code', width: 160, render: (t: string | null) => t ? <Text code>{t}</Text> : <Text type="secondary">—</Text> },
    { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 70 },
    { title: '可见', dataIndex: 'is_visible', key: 'is_visible', width: 70, render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '是' : '否'}</Tag> },
    { title: '系统', dataIndex: 'is_system', key: 'is_system', width: 70, render: (v: boolean) => v ? <Tag color="gold">系统</Tag> : <Tag>自定义</Tag> },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: any, r: ResourceItem) => (
        <Space>
          <a onClick={() => openEdit(r)}><EditOutlined /></a>
          <Popconfirm title="确认删除该资源?" description={r.is_system ? '系统资源不可删除' : undefined} disabled={r.is_system}
            onConfirm={() => handleDelete(r)} okText="删除" okButtonProps={{ danger: true }}>
            <a style={{ color: r.is_system ? 'var(--ice-text-disabled)' : 'var(--ice-danger)' }} onClick={(e) => { if (r.is_system) e.preventDefault() }}><DeleteOutlined /></a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>资源管理（菜单 / 权限码）</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增资源</Button>
      </div>
      <Text type="secondary">菜单由资源驱动（动态菜单）。新增菜单项后，持有对应权限的用户将立即在侧边栏看到它。系统资源（菜单结构、内置权限码）受保护不可删。</Text>
      <Table columns={columns} dataSource={items} rowKey="code" loading={loading} pagination={{ pageSize: 20 }} style={{ marginTop: 12 }} />

      <Modal
        title={editing ? '编辑资源' : '新增资源'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        okText="保存"
        cancelText="取消"
        width={520}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="code" label="资源 Code" rules={[{ required: true, message: '必填' }]} tooltip="全局唯一标识，如 menu.xxx 或 权限码">
            <Input disabled={!!editing} placeholder="menu.example / example.use" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="显示名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="权限/资源的用途说明（可选）" />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select options={TYPE_OPTIONS} disabled={editing?.is_system} />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Input placeholder="general / admin / gallery ..." />
          </Form.Item>
          <Form.Item name="parent_code" label="父级（菜单树）">
            <Select allowClear showSearch optionFilterProp="label" placeholder="顶层（无父级）" options={menuOptions} />
          </Form.Item>
          <Form.Item name="path" label="路由 Path">
            <Input placeholder="/example（菜单点击跳转的路由）" />
          </Form.Item>
          <Form.Item name="permission_code" label="绑定权限码（菜单可见性门控）">
            <Input placeholder="留空=始终可见；填入权限码则该用户需持有" />
          </Form.Item>
          <Form.Item name="icon" label="图标（antd 图标名）">
            <Input placeholder="SettingOutlined / AppstoreOutlined ..." />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_visible" label="是否可见" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}
