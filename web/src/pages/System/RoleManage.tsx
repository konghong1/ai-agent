import { useEffect, useState, useMemo, useRef } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined, SafetyCertificateOutlined,
  DashboardOutlined, MessageOutlined, BookOutlined, ShoppingOutlined,
  PictureOutlined, DatabaseOutlined, ApiOutlined, ToolOutlined,
  AppstoreOutlined, CloudServerOutlined, FileTextOutlined,
  TeamOutlined, ControlOutlined, SettingOutlined, RobotOutlined, SearchOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Switch, Tag, Popconfirm, Drawer, Spin, message, Tree, Badge, Tooltip, Segmented } from 'antd'
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

interface ResourceItem {
  id: number
  code: string
  name: string
  type: string
  category: string
  parent_code: string | null
  path: string | null
  icon: string | null
  permission_code: string | null
  is_visible: boolean
  is_system: boolean
  sort_order: number
}

const CATEGORY_LABEL: Record<string, string> = {
  dashboard: '工作台', chat: '聊天', knowledge: '知识库', 'knowledge-base': '知识库',
  gallery: '电商套图', media: '素材库', memory: '长期记忆', mcp: 'MCP', skill: 'Skill', hook: 'Hook',
  providers: 'AI 提供商', prompt: '提示词模板', team: '团队', admin: '系统管理',
  menu: '菜单',
}

const CATEGORY_ICON: Record<string, React.ReactNode> = {
  dashboard: <DashboardOutlined />, chat: <MessageOutlined />,
  knowledge: <BookOutlined />, 'knowledge-base': <BookOutlined />,
  gallery: <ShoppingOutlined />, media: <PictureOutlined />,
  memory: <DatabaseOutlined />, mcp: <ApiOutlined />,
  skill: <AppstoreOutlined />, hook: <ToolOutlined />,
  providers: <CloudServerOutlined />, prompt: <FileTextOutlined />,
  team: <TeamOutlined />, admin: <ControlOutlined />,
  menu: <AppstoreOutlined />,
}

const ICON_COMPONENTS: Record<string, React.ReactNode> = {
  DashboardOutlined: <DashboardOutlined />,
  RobotOutlined: <RobotOutlined />,
  TeamOutlined: <TeamOutlined />,
  SettingOutlined: <SettingOutlined />,
  CloudServerOutlined: <CloudServerOutlined />,
  AppstoreOutlined: <AppstoreOutlined />,
  DatabaseOutlined: <DatabaseOutlined />,
  MessageOutlined: <MessageOutlined />,
  BookOutlined: <BookOutlined />,
  ShoppingOutlined: <ShoppingOutlined />,
  PictureOutlined: <PictureOutlined />,
  ApiOutlined: <ApiOutlined />,
  ToolOutlined: <ToolOutlined />,
  ControlOutlined: <ControlOutlined />,
}

/** 将扁平 catalog 构建为 antd Tree 的 treeData（分类 → 权限码 两级树） */
function buildCategoryTree(catalog: CatalogItem[]): { nodes: any[]; permToLeaf: Map<string, string[]>; keyToPerm: Map<string, string[]> } {
  // 注意：下面的 `||` 短路曾导致 set 永不执行、catMap 始终为空（分类树渲染空白）。
  // 这里显式写入新数组，确保分类正确聚合。
  const catMap = new Map<string, CatalogItem[]>()
  for (const c of catalog) {
    const arr = catMap.get(c.category) || []
    arr.push(c)
    catMap.set(c.category, arr)
  }
  const permToLeaf = new Map<string, string[]>()
  const keyToPerm = new Map<string, string[]>()
  const nodes = Array.from(catMap.entries())
    .sort(([a], [b]) => (CATEGORY_LABEL[a] || a).localeCompare(CATEGORY_LABEL[b] || b, 'zh'))
    .map(([cat, items]) => {
      const childCodes = items.map(p => p.code)
      const parentKey = `__cat__${cat}`
      keyToPerm.set(parentKey, childCodes)
      return {
        key: parentKey,
        titleText: CATEGORY_LABEL[cat] || cat,
        title: (
          <span>
            {CATEGORY_ICON[cat] || null}
            {' '}{CATEGORY_LABEL[cat] || cat}
            <Badge count={items.length} size="small" style={{ marginLeft: 6 }} />
          </span>
        ),
        children: items
          .sort((a, b) => (a.name).localeCompare(b.name, 'zh'))
          .map((p) => {
            // 叶子 key 加 `perm::` 前缀，并登记 code→叶子key 映射（每个分类权限码唯一）
            const k = `perm::${p.code}`
            permToLeaf.set(p.code, [k])
            keyToPerm.set(k, [p.code])
            return {
              key: k,
              titleText: p.name,
              title: (
                <Tooltip title={p.description || undefined} placement="right">
                  <span>{p.name}</span>
                </Tooltip>
              ),
              isLeaf: true,
            }
          }),
      }
    })
  return { nodes, permToLeaf, keyToPerm }
}

/** 将菜单资源和权限目录构建为菜单树结构（菜单节点 + 其关联的权限码） */
function buildMenuTree(menus: ResourceItem[], permissions: CatalogItem[]): { nodes: any[]; permToLeaf: Map<string, string[]>; keyToPerm: Map<string, string[]> } {
  const menuMap = new Map<string, ResourceItem>()
  menus.forEach(m => menuMap.set(m.code, m))

  // 权限按 code 索引（避免每次递归线性查找）
  const permByCode = new Map<string, CatalogItem>()
  permissions.forEach(p => permByCode.set(p.code, p))

  // code → 该权限对应的全部叶子 key。多个菜单可共享同一 permission_code，
  // 因此一个 code 可能映射到多个叶子 key；同时 key 必须全局唯一，否则 antd
  // Tree 的 keyEntities 缓存会合并 children，导致展开/收起时子节点不断翻倍。
  const permToLeaf = new Map<string, string[]>()
  // 任意节点 key → 它代表的全部权限码（含子孙）。antd 在全选父节点时会把
  // checkedKeys 收缩为父 key，勾选/取消时必须能据此还原出真实权限码集合。
  const keyToPerm = new Map<string, string[]>()

  // 收集某菜单（含其全部子孙）所关联的所有权限码
  const collectMenuPermCodes = (menu: ResourceItem): string[] => {
    let codes: string[] = []
    menus.filter(m => m.parent_code === menu.code).forEach(child => {
      codes = codes.concat(collectMenuPermCodes(child))
    })
    if (menu.permission_code && permByCode.has(menu.permission_code)) codes.push(menu.permission_code)
    return codes
  }

  function buildNode(menu: ResourceItem, allMenus: ResourceItem[]): any {
    const children = allMenus.filter(m => m.parent_code === menu.code)
    const iconComp = menu.icon && ICON_COMPONENTS[menu.icon] ? ICON_COMPONENTS[menu.icon] : null

    const nodeChildren: any[] = []

    // 1. 添加子菜单节点
    children.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)).forEach(child => {
      nodeChildren.push(buildNode(child, allMenus))
    })

    // 2. 如果菜单绑定了权限码，添加该权限节点（key 唯一化：perm::权限码::菜单code）
    if (menu.permission_code) {
      const perm = permByCode.get(menu.permission_code)
      if (perm) {
        const k = `perm::${perm.code}::${menu.code}`
        keyToPerm.set(k, [perm.code])
        const arr = permToLeaf.get(perm.code) || []
        arr.push(k)
        permToLeaf.set(perm.code, arr)
        nodeChildren.push({
          key: k,
          titleText: perm.name,
          title: (
            <Tooltip title={perm.description || undefined} placement="right">
              <span>
                <Tag color="purple" style={{ marginLeft: 4, fontSize: 11 }}>权限</Tag>
                {' '}{perm.name}
              </span>
            </Tooltip>
          ),
          isLeaf: true,
        })
      }
    }

    const menuKey = `menu::${menu.code}`
    keyToPerm.set(menuKey, collectMenuPermCodes(menu))
    return {
      key: menuKey,
      titleText: menu.name,
      title: (
        <span>
          {iconComp}
          {' '}{menu.name}
          {menu.permission_code && <Tag color="blue" style={{ marginLeft: 4, fontSize: 11 }}>需权限</Tag>}
        </span>
      ),
      children: nodeChildren.length > 0 ? nodeChildren : undefined,
    }
  }

  // 构建顶层菜单
  const rootMenus = menus.filter(m => !m.parent_code)
  const nodes = rootMenus
    .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
    .map(m => buildNode(m, menus))
  return { nodes, permToLeaf, keyToPerm }
}

/** 按关键字过滤树：保留命中节点及其祖先链，隐藏无关分支 */
function filterTreeByText(nodes: any[], keyword: string): any[] {
  const lower = keyword.toLowerCase()
  const walk = (ns: any[]): any[] => ns
    .map((n) => {
      const children = n.children ? walk(n.children) : undefined
      const selfMatch = (n.titleText || '').toLowerCase().includes(lower)
      if (selfMatch) return n
      if (children && children.length) return { ...n, children }
      return null
    })
    .filter(Boolean)
  return walk(nodes)
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
  const [menus, setMenus] = useState<ResourceItem[]>([])
  const [checked, setChecked] = useState<string[]>([])
  const [permLoading, setPermLoading] = useState(false)
  const [savingPerm, setSavingPerm] = useState(false)
  const [viewMode, setViewMode] = useState<'menu' | 'category'>('menu') // 视图切换

  // 受控展开（取代 defaultExpandAll，避免 antd 内部缓存合并 children 导致的翻倍）
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [autoExpandParent, setAutoExpandParent] = useState(true)
  const [searchValue, setSearchValue] = useState('')
  const treeRef = useRef<any>(null)

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
      const [catRes, permRes, menuRes] = await Promise.all([
        fetch('/api/permissions/catalog', { headers: authHeaders() }),
        fetch(`/api/system/roles/${r.id}/permissions`, { headers: authHeaders() }),
        fetch('/api/system/resources?type=menu', { headers: authHeaders() }),
      ])
      const cat = await catRes.json()
      const perm = await permRes.json()
      const menuData = await menuRes.json()
      setCatalog(cat.items || [])
      setMenus(menuData.items || [])
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

  // 勾选回调：antd 在 checkStrictly=false 下会把「全选的父节点」收缩为父 key，
  // 因此需借助 keyToPerm 把任意节点 key（叶子或菜单）还原为其代表的全部权限码。
  // 关键是：只替换「当前树能代表的那部分码」，其余码保留，防止权限被静默抹除。
  const onTreeCheck = (checkedKeys: any) => {
    const keys = Array.isArray(checkedKeys) ? checkedKeys : (checkedKeys as any).checked || []
    const newTreeCodes = new Set<string>()
    ;(keys as string[]).forEach((k: string) => {
      const p = activeTree.keyToPerm.get(k)
      if (p) p.forEach((c) => newTreeCodes.add(c))
    })
    setChecked((prev) => {
      const kept = prev.filter((c) => !treeRepresented.has(c))
      return Array.from(new Set([...kept, ...newTreeCodes]))
    })
  }

  // 搜索：根据 titleText 过滤并自动展开命中节点的祖先链
  const onSearchChange = (e: any) => {
    const val = e?.target?.value ?? ''
    setSearchValue(val)
    if (!val) {
      const all: string[] = []
      const walk = (ns: any[]) => ns.forEach((n) => { all.push(n.key); if (n.children) walk(n.children) })
      walk(treeData)
      setExpandedKeys(all)
      setAutoExpandParent(true)
      return
    }
    const lower = val.toLowerCase()
    const matched: string[] = []
    const walk = (ns: any[], parents: string[] = []) => ns.forEach((n) => {
      if ((n.titleText || '').toLowerCase().includes(lower)) matched.push(...parents, n.key)
      if (n.children) walk(n.children, [...parents, n.key])
    })
    walk(treeData)
    setExpandedKeys(Array.from(new Set(matched)))
    setAutoExpandParent(true)
  }

  // 树状权限数据（从 catalog / menus 构建）
  const categoryTree = useMemo(() => buildCategoryTree(catalog), [catalog])
  const menuTree = useMemo(() => buildMenuTree(menus, catalog), [menus, catalog])
  const activeTree = viewMode === 'menu' ? menuTree : categoryTree
  const treeData = activeTree.nodes
  // 搜索时过滤展示树（隐藏无关分支，保证搜索真正生效）
  const displayTree = useMemo(
    () => (searchValue ? filterTreeByText(treeData, searchValue) : treeData),
    [treeData, searchValue],
  )

  // 把角色已授权的权限码映射回当前树的叶子 key（同一权限码可能对应多个叶子）
  const treeCheckedKeys = useMemo(
    () => checked.flatMap((c) => activeTree.permToLeaf.get(c) || []),
    [checked, activeTree],
  )

  // 当前树「能代表」的全部权限码（菜单视图只覆盖子集，分类视图覆盖全部）。
  // 用于勾选时做 delta 合并：只更新树内码，树外码（当前视图不可见）一律保留，
  // 避免点一下勾选框就丢失大量树外权限。
  const treeRepresented = useMemo(
    () => new Set(activeTree.permToLeaf.keys()),
    [activeTree],
  )

  // 树数据变化时默认展开全部
  useEffect(() => {
    const all: string[] = []
    const walk = (ns: any[]) => ns.forEach((n) => { all.push(n.key); if (n.children) walk(n.children) })
    walk(treeData)
    setExpandedKeys(all)
    setAutoExpandParent(true)
  }, [treeData])

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
        width={600}
        footer={<Space style={{ float: 'right' }}>
          <Button onClick={() => setDrawerOpen(false)}>取消</Button>
          <Button type="primary" loading={savingPerm} onClick={savePerms}>保存权限</Button>
        </Space>}
      >
        {permLoading ? <Spin /> : (
          <div>
            <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
              <Segmented
                value={viewMode}
                onChange={(v) => setViewMode(v as 'menu' | 'category')}
                options={[
                  { label: '按菜单树', value: 'menu' },
                  { label: '按功能分类', value: 'category' },
                ]}
              />
              <Input
                allowClear
                prefix={<SearchOutlined style={{ color: 'var(--ice-text-disabled)' }} />}
                placeholder="搜索菜单或权限…"
                value={searchValue}
                onChange={onSearchChange}
                style={{ width: 220 }}
              />
            </div>

            <div className="perm-tree-card">
              <Tree
                ref={treeRef}
                className="rbac-perm-tree"
                checkable
                blockNode
                treeData={displayTree}
                expandedKeys={expandedKeys}
                autoExpandParent={autoExpandParent}
                onExpand={(keys) => { setExpandedKeys(keys as string[]); setAutoExpandParent(false) }}
                checkedKeys={treeCheckedKeys}
                onCheck={onTreeCheck}
                style={{ background: 'transparent' }}
              />
            </div>

            <div style={{ marginTop: 10, fontSize: 12, color: 'var(--ice-text-secondary)' }}>
              已选 <b style={{ color: 'var(--ice-primary)' }}>{checked.length}</b> 项权限
              {viewMode === 'menu' && (
                <span style={{ marginLeft: 8, opacity: 0.7 }}>勾选父菜单可对其下全部权限一键授权</span>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </IceCrystalCard>
  )
}
