import { useEffect, useMemo, useState } from 'react'
import {
  Card, Table, Button, Modal, Checkbox, Tag, message, Space, Typography,
  Empty, Tabs, Input, Popconfirm, Select,
} from 'antd'
import { useAuthStore } from '@/stores/auth'

const { Title, Text } = Typography
const { TextArea } = Input

interface CatalogItem {
  code: string
  name: string
  category: string
  is_system: boolean
  grantable: boolean
}
interface Team {
  id: number
  name: string
  slug: string
  description: string
}
interface Member {
  user_id: number
  username: string
  email: string
  role: string
  permissions: string[]
}
interface JoinReq {
  id: number
  user_id: number
  username: string
  email: string
  message: string
  status: string
  created_at: string | null
}
interface Invite {
  id: number
  email: string
  role: string
  status: string
  message: string | null
  created_at: string | null
}
interface MyReq {
  id: number
  team_id: number
  team_name: string
  status: string
  message: string
  review_comment: string
  created_at: string | null
}
interface MyInv {
  id: number
  team_id: number
  team_name: string
  role: string
  message: string | null
  status: string
  created_at: string | null
}

// 权限分类中文标签（catalog.category → 展示名）
const CAT_LABELS: Record<string, string> = {
  dashboard: '仪表盘', chat: '聊天', 'knowledge-base': '知识库', gallery: '电商套图',
  media: '媒体库', memory: '长期记忆', mcp: 'MCP', skill: 'Skill', hook: 'Hook',
  team: '团队', admin: '系统管理', providers: 'AI 提供商', prompt: '提示词模板',
}

export default function Teams() {
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const canManage = !!(user?.is_superuser || user?.is_team_admin)

  const auth = () => ({ Authorization: `Bearer ${token}` })
  const api = async (path: string, opts: RequestInit = {}) => {
    const res = await fetch(path, { ...opts, headers: { ...auth(), 'Content-Type': 'application/json', ...(opts.headers || {}) } })
    if (!res.ok) {
      const e = await res.json().catch(() => ({}))
      throw new Error(e.detail || `HTTP ${res.status}`)
    }
    return res.json()
  }

  const [teams, setTeams] = useState<Team[]>([])
  const [catalog, setCatalog] = useState<CatalogItem[]>([])
  const [activeTeam, setActiveTeam] = useState<Team | null>(null)

  // 成员与权限分配（团队管理员）
  const [members, setMembers] = useState<Member[]>([])
  const [permModalOpen, setPermModalOpen] = useState(false)
  const [editing, setEditing] = useState<Member | null>(null)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)

  // 待审申请 / 邀请（团队管理员）
  const [pending, setPending] = useState<JoinReq[]>([])
  const [invites, setInvites] = useState<Invite[]>([])
  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewTarget, setReviewTarget] = useState<JoinReq | null>(null)
  const [reviewComment, setReviewComment] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')

  // 普通用户视角
  const [discover, setDiscover] = useState<Team[]>([])
  const [myReqs, setMyReqs] = useState<MyReq[]>([])
  const [myInvs, setMyInvs] = useState<MyInv[]>([])
  const [loading, setLoading] = useState(false)

  const loadTeams = async () => {
    setLoading(true)
    try {
      const [t, c] = await Promise.all([
        api('/api/teams'),
        api('/api/permissions/catalog'),
      ])
      setTeams(t.teams || [])
      setCatalog(c.items || [])
      if ((t.teams || []).length > 0 && !activeTeam) setActiveTeam(t.teams[0])
    } catch (e: any) {
      message.error(e.message || '加载团队失败')
    } finally {
      setLoading(false)
    }
  }

  const loadMembers = async (teamId: number) => {
    try {
      const r = await api(`/api/teams/${teamId}/members`)
      setMembers(r.members || [])
    } catch (e: any) {
      message.error(e.message || '加载成员失败')
    }
  }

  const loadPending = async (teamId: number) => {
    try {
      const r = await api(`/api/teams/${teamId}/join-requests`)
      setPending(r.join_requests || [])
    } catch { /* 非团队管理员会 403，忽略 */ setPending([]) }
  }
  const loadInvites = async (teamId: number) => {
    try {
      const r = await api(`/api/teams/${teamId}/invites`)
      setInvites(r.invites || [])
    } catch { setInvites([]) }
  }

  const loadDiscover = async () => {
    try { const r = await api('/api/teams/discover'); setDiscover(r.teams || []) } catch { setDiscover([]) }
  }
  const loadMyReqs = async () => {
    try { const r = await api('/api/me/join-requests'); setMyReqs(r.join_requests || []) } catch { setMyReqs([]) }
  }
  const loadMyInvs = async () => {
    try { const r = await api('/api/me/invites'); setMyInvs(r.invites || []) } catch { setMyInvs([]) }
  }

  useEffect(() => { loadTeams() }, [])
  useEffect(() => { if (activeTeam) { loadMembers(activeTeam.id); if (canManage) { loadPending(activeTeam.id); loadInvites(activeTeam.id) } } }, [activeTeam, canManage])
  useEffect(() => { loadDiscover(); loadMyReqs(); loadMyInvs() }, [])

  // ── 权限分配（沿用既有逻辑）──
  const grantable = useMemo(() => catalog.filter((c) => c.grantable && !c.is_system), [catalog])
  const grouped = useMemo(() => {
    const g: Record<string, CatalogItem[]> = {}
    grantable.forEach((c) => { if (!g[c.category]) g[c.category] = []; g[c.category].push(c) })
    return g
  }, [grantable])

  const openPermModal = (m: Member) => {
    setEditing(m)
    const init: Record<string, boolean> = {}
    grantable.forEach((c) => (init[c.code] = m.permissions.includes(c.code)))
    setChecked(init)
    setPermModalOpen(true)
  }
  const savePerm = async () => {
    if (!editing || !activeTeam) return
    const codes = Object.keys(checked).filter((k) => checked[k])
    setSaving(true)
    try {
      await api(`/api/teams/${activeTeam.id}/members/${editing.user_id}/permissions`, {
        method: 'POST', body: JSON.stringify({ permission_codes: codes }),
      })
      message.success(`已保存 ${editing.username} 的团队权限（${codes.length} 项）`)
      setPermModalOpen(false)
      await loadMembers(activeTeam.id)
    } catch (e: any) { message.error(e.message || '保存失败') } finally { setSaving(false) }
  }

  // ── 申请审批 ──
  const openReview = (r: JoinReq) => { setReviewTarget(r); setReviewComment(''); setReviewOpen(true) }
  const submitReview = async (action: 'approve' | 'reject') => {
    if (!reviewTarget || !activeTeam) return
    setSaving(true)
    try {
      await api(`/api/teams/${activeTeam.id}/join-requests/${reviewTarget.id}/review`, {
        method: 'POST', body: JSON.stringify({ action, comment: reviewComment }),
      })
      message.success(action === 'approve' ? '已通过申请' : '已拒绝申请')
      setReviewOpen(false)
      await loadPending(activeTeam.id)
      await loadMembers(activeTeam.id)
    } catch (e: any) { message.error(e.message || '操作失败') } finally { setSaving(false) }
  }

  // ── 邀请 ──
  const sendInvite = async () => {
    if (!activeTeam || !inviteEmail.trim()) { message.warning('请输入受邀邮箱'); return }
    setSaving(true)
    try {
      await api(`/api/teams/${activeTeam.id}/invites`, {
        method: 'POST', body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
      })
      message.success(`已邀请 ${inviteEmail}`)
      setInviteEmail('')
      await loadInvites(activeTeam.id)
    } catch (e: any) { message.error(e.message || '邀请失败') } finally { setSaving(false) }
  }

  // ── 普通用户：申请加入 ──
  const applyTeam = async (tid: number) => {
    try {
      await api(`/api/teams/${tid}/join-requests`, { method: 'POST', body: JSON.stringify({ message: '' }) })
      message.success('已提交加入申请，请等待审批')
      await loadDiscover(); await loadMyReqs()
    } catch (e: any) { message.error(e.message || '申请失败') }
  }
  // ── 普通用户：响应邀请 ──
  const respondInvite = async (iid: number, action: 'accept' | 'decline') => {
    try {
      await api(`/api/invites/${iid}/respond`, { method: 'POST', body: JSON.stringify({ action }) })
      message.success(action === 'accept' ? '已加入团队' : '已拒绝邀请')
      await loadMyInvs()
    } catch (e: any) { message.error(e.message || '操作失败') }
  }

  // ── 表格列 ──
  const memberCols = [
    { title: '用户名', dataIndex: 'username' },
    { title: '邮箱', dataIndex: 'email' },
    { title: '角色', dataIndex: 'role', render: (r: string) => <Tag color={r === 'owner' ? 'gold' : r === 'admin' ? 'blue' : 'default'}>{r}</Tag> },
    {
      title: '已授权', key: 'perms',
      render: (_: any, m: Member) =>
        m.permissions.length === 0 ? <Text type="secondary">—</Text> : (
          <Space wrap size={[4, 4]}>
            {m.permissions.slice(0, 5).map((p) => <Tag key={p}>{p}</Tag>)}
            {m.permissions.length > 5 && <Tag>+{m.permissions.length - 5}</Tag>}
          </Space>
        ),
    },
    ...(canManage ? [{
      title: '操作', key: 'op',
      render: (_: any, m: Member) => <Button type="link" onClick={() => openPermModal(m)}>分配权限</Button>,
    }] : []),
  ]

  const statusTag = (s: string) => {
    const map: Record<string, string> = { pending: 'gold', approved: 'green', rejected: 'red', accepted: 'green', declined: 'red', active: 'green' }
    const label: Record<string, string> = { pending: '待审批', approved: '已通过', rejected: '已拒绝', accepted: '已接受', declined: '已拒绝', active: '活跃' }
    return <Tag color={map[s] || 'default'}>{label[s] || s}</Tag>
  }

  const pendingCols = [
    { title: '申请人', dataIndex: 'username' },
    { title: '邮箱', dataIndex: 'email' },
    { title: '留言', dataIndex: 'message', render: (v: string) => v || <Text type="secondary">—</Text> },
    { title: '状态', dataIndex: 'status', render: (s: string) => statusTag(s) },
    {
      title: '操作', key: 'op',
      render: (_: any, r: JoinReq) => (
        <Space>
          <Button type="link" onClick={() => openReview(r)}>审批</Button>
        </Space>
      ),
    },
  ]

  const inviteCols = [
    { title: '邮箱', dataIndex: 'email' },
    { title: '角色', dataIndex: 'role' },
    { title: '状态', dataIndex: 'status', render: (s: string) => statusTag(s) },
  ]

  const discoverCols = [
    { title: '团队', dataIndex: 'name' },
    { title: '描述', dataIndex: 'description', render: (v: string) => v || <Text type="secondary">—</Text> },
    { title: '操作', key: 'op', render: (_: any, t: Team) => <Button type="primary" onClick={() => applyTeam(t.id)}>申请加入</Button> },
  ]

  const myReqCols = [
    { title: '团队', dataIndex: 'team_name' },
    { title: '状态', dataIndex: 'status', render: (s: string) => statusTag(s) },
    { title: '审批备注', dataIndex: 'review_comment', render: (v: string) => v || <Text type="secondary">—</Text> },
  ]

  const myInvCols = [
    { title: '团队', dataIndex: 'team_name' },
    { title: '角色', dataIndex: 'role' },
    { title: '状态', dataIndex: 'status', render: (s: string) => statusTag(s) },
    {
      title: '操作', key: 'op',
      render: (_: any, i: MyInv) => i.status === 'pending' ? (
        <Space>
          <Button type="link" onClick={() => respondInvite(i.id, 'accept')}>接受</Button>
          <Popconfirm title="确定拒绝该邀请？" onConfirm={() => respondInvite(i.id, 'decline')}>
            <Button type="link" danger>拒绝</Button>
          </Popconfirm>
        </Space>
      ) : <Text type="secondary">已处理</Text>,
    },
  ]

  const spaceTab = (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
      <Card title="我的团队" style={{ width: 260, flexShrink: 0 }}>
        {teams.length === 0 ? <Empty description="暂无团队" /> : (
          <Space direction="vertical" style={{ width: '100%' }}>
            {teams.map((t) => (
              <Button key={t.id} block type={activeTeam?.id === t.id ? 'primary' : 'default'} onClick={() => setActiveTeam(t)}>
                {t.name}
              </Button>
            ))}
          </Space>
        )}
      </Card>
      <Card title={activeTeam ? `成员 · ${activeTeam.name}` : '成员'} style={{ flex: 1 }}>
        {!activeTeam ? <Empty description="请选择左侧团队" /> : (
          <Tabs
            items={[
              { key: 'members', label: '成员', children: <Table rowKey="user_id" dataSource={members} columns={memberCols} pagination={false} /> },
              ...(canManage ? [{
                key: 'pending', label: `待审申请${pending.length ? ` (${pending.length})` : ''}`,
                children: (
                  <Table rowKey="id" dataSource={pending} columns={pendingCols} pagination={false}
                    locale={{ emptyText: '暂无待审申请' }} />
                ),
              }] : []),
              ...(canManage ? [{
                key: 'invites', label: '邀请管理',
                children: (
                  <div>
                    <Space style={{ marginBottom: 12 }}>
                      <Input placeholder="受邀人邮箱" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} style={{ width: 240 }} />
                      <Select value={inviteRole} onChange={setInviteRole} style={{ width: 120 }} options={[{ value: 'member', label: '成员' }, { value: 'admin', label: '管理员' }]} />
                      <Button type="primary" loading={saving} onClick={sendInvite}>发送邀请</Button>
                    </Space>
                    <Table rowKey="id" dataSource={invites} columns={inviteCols} pagination={false} locale={{ emptyText: '暂无邀请' }} />
                  </div>
                ),
              }] : []),
            ]}
          />
        )}
      </Card>
    </div>
  )

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <Title level={3}>团队</Title>
      <Text type="secondary">
        团队管理员可在此管理成员、审批加入申请、邀请成员；普通用户可发现团队并提交申请，或响应收到的邀请。
      </Text>
      <div style={{ marginTop: 16 }}>
        <Tabs
          items={[
            { key: 'space', label: '团队空间', children: spaceTab },
            { key: 'discover', label: '发现团队', children: (
              <Card>
                <Table rowKey="id" loading={loading} dataSource={discover} columns={discoverCols} pagination={false} locale={{ emptyText: '暂无可申请的团队' }} />
              </Card>
            ) },
            { key: 'myreq', label: `我的申请${myReqs.length ? ` (${myReqs.length})` : ''}`, children: (
              <Card>
                <Table rowKey="id" dataSource={myReqs} columns={myReqCols} pagination={false} locale={{ emptyText: '你还没有提交过加入申请' }} />
              </Card>
            ) },
            { key: 'myinv', label: `我的邀请${myInvs.length ? ` (${myInvs.length})` : ''}`, children: (
              <Card>
                <Table rowKey="id" dataSource={myInvs} columns={myInvCols} pagination={false} locale={{ emptyText: '你还没有收到邀请' }} />
              </Card>
            ) },
          ]}
        />
      </div>

      {/* 成员权限分配 */}
      <Modal
        title={editing ? `分配权限 · ${editing.username}` : ''}
        open={permModalOpen} onCancel={() => setPermModalOpen(false)} onOk={savePerm}
        confirmLoading={saving} width={720}
      >
        <Text type="secondary">仅能分配你被授予范围内的功能：</Text>
        <div style={{ maxHeight: 420, overflowY: 'auto', marginTop: 12 }}>
          {Object.entries(grouped).map(([cat, items]) => (
            <div key={cat} style={{ marginBottom: 16 }}>
              <Title level={5} style={{ marginBottom: 8 }}>{CAT_LABELS[cat] || cat}</Title>
              <Space wrap size={[8, 8]}>
                {items.map((c) => (
                  <Checkbox key={c.code} checked={!!checked[c.code]}
                    onChange={(e) => setChecked((p) => ({ ...p, [c.code]: e.target.checked }))}>
                    {c.name}
                  </Checkbox>
                ))}
              </Space>
            </div>
          ))}
          {grantable.length === 0 && <Text type="secondary">你当前没有可授予的功能范围。</Text>}
        </div>
      </Modal>

      {/* 申请审批 */}
      <Modal
        title="审批加入申请"
        open={reviewOpen} onCancel={() => setReviewOpen(false)} okText="通过" okButtonProps={{ loading: saving }}
        onOk={() => submitReview('approve')}
        footer={[
          <Button key="reject" danger loading={saving} onClick={() => submitReview('reject')}>拒绝</Button>,
          <Button key="ok" type="primary" loading={saving} onClick={() => submitReview('approve')}>通过</Button>,
        ]}
      >
        {reviewTarget && (
          <div>
            <p>申请人：<b>{reviewTarget.username}</b>（{reviewTarget.email}）</p>
            <p>留言：{reviewTarget.message || '—'}</p>
            <TextArea rows={3} placeholder="审批备注（可选）" value={reviewComment} onChange={(e) => setReviewComment(e.target.value)} />
          </div>
        )}
      </Modal>
    </div>
  )
}
