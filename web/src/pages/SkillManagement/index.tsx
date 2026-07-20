import { useEffect, useState } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined, SafetyOutlined, CheckCircleOutlined, CodeOutlined, FolderOutlined, GlobalOutlined, GithubOutlined, CopyOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Tag, message, Alert, Popconfirm, InputNumber, Card, Divider } from 'antd'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

interface SkillItem {
  id: number
  name: string
  title: string
  description: string
  source_type: string
  path: string
  content: string
  trigger_words: string[]
  declared_hooks: Record<string, any>
  version: number
  enabled: boolean
}

const SOURCE_OPTIONS = [
  { value: 'inline', label: '内联（直接编写指令）', icon: <CodeOutlined />, color: 'blue' },
  { value: 'local', label: '本地', icon: <FolderOutlined />, color: 'green' },
  { value: 'remote', label: '远程', icon: <GlobalOutlined />, color: 'orange' },
  { value: 'repo', label: '仓库', icon: <GithubOutlined />, color: 'purple' },
]

const SOURCE_META: Record<string, {
  label: string
  pathLabel: string
  pathPlaceholder: string
  pathPrefix?: string
  pathHelp?: React.ReactNode
  contentLabel: string
  contentPlaceholder: string
  contentRequired: boolean
  contentRows: number
  panelTitle: string
  panelDesc: string
  accent: string
}> = {
  inline: {
    label: '内联（直接编写指令）',
    pathLabel: '路径',
    pathPlaceholder: '',
    contentLabel: '技能指令正文（Markdown，聊天中按需加载）',
    contentPlaceholder: '# 技能步骤\n1. 当用户提到 PDF 时...\n2. 调用相关工具...',
    contentRequired: true,
    contentRows: 8,
    panelTitle: '直接编写指令',
    panelDesc: '在下方文本框中直接编写技能的 Markdown 指令。聊天中模型会根据触发词自动加载这段内容。',
    accent: '#1677ff',
  },
  local: {
    label: '本地',
    pathLabel: '本地路径',
    pathPlaceholder: '/home/user/.workbuddy/skills/my-skill/SKILL.md',
    pathHelp: '支持绝对路径，指向本地 Skill 目录或 SKILL.md 文件。',
    contentLabel: '覆盖指令（可选）',
    contentPlaceholder: '留空则读取本地文件；填写后将优先使用此覆盖内容。',
    contentRequired: false,
    contentRows: 4,
    panelTitle: '加载本地 Skill',
    panelDesc: '填写本地文件路径。系统将读取该路径对应的 SKILL.md 作为技能正文。',
    accent: '#52c41a',
  },
  remote: {
    label: '远程',
    pathLabel: '远程 URL',
    pathPlaceholder: 'https://example.com/skills/my-skill/SKILL.md',
    pathHelp: '支持 HTTP/HTTPS 地址，指向远程 SKILL.md 文件。',
    contentLabel: '覆盖指令（可选）',
    contentPlaceholder: '留空则拉取远程内容；填写后将优先使用此覆盖内容。',
    contentRequired: false,
    contentRows: 4,
    panelTitle: '拉取远程 Skill',
    panelDesc: '填写可访问的远程 URL。系统将下载该地址内容作为技能正文。',
    accent: '#fa8c16',
  },
  repo: {
    label: '仓库',
    pathLabel: '仓库地址',
    pathPlaceholder: 'https://github.com/username/repo.git',
    pathHelp: '支持 https:// 或 git@ 开头的 Git 仓库地址。',
    contentLabel: '覆盖指令（可选）',
    contentPlaceholder: '留空则使用仓库默认 SKILL.md；填写后将优先使用此覆盖内容。',
    contentRequired: false,
    contentRows: 4,
    panelTitle: '从仓库导入',
    panelDesc: '填写 Git 仓库地址。系统将克隆/读取仓库中的 SKILL.md 作为技能正文。',
    accent: '#722ed1',
  },
}

export default function SkillManagement() {
  const [items, setItems] = useState<SkillItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<SkillItem | null>(null)
  const [gate, setGate] = useState<{ id: number; passed: boolean; errors: string[]; warnings: string[] } | null>(null)
  const [form] = Form.useForm()
  const sourceType = Form.useWatch('source_type', form) || 'inline'
  const meta = SOURCE_META[sourceType] || SOURCE_META.inline

  const fetchItems = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/skills', { headers: authHeaders() })
      if (r.ok) { const data = await r.json(); setItems(Array.isArray(data) ? data : []) }
    } catch { /* */ } finally { setLoading(false) }
  }
  useEffect(() => { fetchItems() }, [])

  const openCreate = () => {
    setEditing(null); setGate(null); form.resetFields()
    form.setFieldsValue({ source_type: 'inline', enabled: false, version: 1, trigger_words: [], declared_hooks: '{}', path: '', content: '' })
    setModalOpen(true)
  }

  const openEdit = async (r: SkillItem) => {
    setEditing(r); setGate(null); form.resetFields()
    // 编辑时拉取完整详情，回填 content / path 等列表未返回的字段
    let detail: SkillItem | null = null
    try {
      const res = await fetch(`/api/skills/${r.id}`, { headers: authHeaders() })
      if (res.ok) detail = await res.json()
    } catch { /* */ }
    const base = detail || r
    form.setFieldsValue({
      ...base,
      path: base.path || '',
      content: base.content || '',
      declared_hooks: JSON.stringify(base.declared_hooks || {}, null, 2),
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const v = await form.validateFields()
      let declared: Record<string, any> = {}
      try { declared = v.declared_hooks ? JSON.parse(v.declared_hooks) : {} } catch { message.error('声明式 Hook 不是合法 JSON'); return }
      const payload = {
        name: v.name, title: v.title, description: v.description || '',
        source_type: v.source_type, path: (v.path || '').trim(), content: v.content || '',
        trigger_words: v.trigger_words || [], declared_hooks: declared, version: v.version || 1,
        enabled: false,
      }
      const url = editing ? `/api/skills/${editing.id}` : '/api/skills'
      const res = await fetch(url, { method: editing ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(payload) })
      if (res.ok) { message.success('已保存，请先「安全检测」再「启用」'); setModalOpen(false); fetchItems() }
      else { const e = await res.json().catch(() => ({})); message.error(e.detail || e.message || '保存失败') }
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message || '保存失败') }
  }

  const runGate = async (r: SkillItem) => {
    const res = await fetch(`/api/skills/${r.id}/security-check`, { method: 'POST', headers: authHeaders() })
    const data = await res.json()
    setGate({ id: r.id, passed: !!data.passed, errors: data.errors || [], warnings: data.warnings || [] })
  }
  const handleEnable = async (r: SkillItem) => {
    const res = await fetch(`/api/skills/${r.id}/enable`, { method: 'POST', headers: authHeaders() })
    if (res.ok) { const d = await res.json(); message.success(`技能已启用${d.linked_hooks ? `（联动 ${d.linked_hooks} 个 Hook）` : ''}`); fetchItems() }
    else { const e = await res.json().catch(() => ({})); message.error((e.detail && e.detail.message) || e.message || '启用失败') }
  }
  const handleDelete = async (id: number) => { await fetch(`/api/skills/${id}`, { method: 'DELETE', headers: authHeaders() }); fetchItems() }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', render: (t: string) => <Text strong style={{ color: 'var(--ice-text-primary)' }}>{t}</Text> },
    { title: '标题', dataIndex: 'title', key: 'title', render: (t: string) => <Text style={{ color: 'var(--ice-text-secondary)' }}>{t}</Text> },
    { title: '类型', dataIndex: 'source_type', key: 'type', width: 130, render: (t: string) => {
      const opt = SOURCE_OPTIONS.find(o => o.value === t) || SOURCE_OPTIONS[0]
      return <Tag icon={opt.icon} color={opt.color}>{opt.label}</Tag>
    }},
    { title: '触发词', dataIndex: 'trigger_words', key: 'tw', render: (t: string[]) => (t || []).map((w) => <Tag key={w} color="blue">{w}</Tag>) },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 90, render: (e: boolean) => e ? <Tag color="success">已启用</Tag> : <Tag>未启用</Tag> },
    {
      title: '操作', key: 'action', width: 220,
      render: (_: any, r: SkillItem) => (
        <Space size="small">
          <a onClick={() => runGate(r)}><SafetyOutlined /> 检测</a>
          <a style={{ color: r.enabled ? 'var(--ice-text-secondary)' : 'var(--ice-primary)' }} onClick={() => handleEnable(r)}><CheckCircleOutlined /> 启用</a>
          <a onClick={() => openEdit(r)}><EditOutlined /></a>
          <Popconfirm title="确认删除该技能？" onConfirm={() => handleDelete(r.id)}>
            <a style={{ color: 'var(--ice-danger)' }}><DeleteOutlined /></a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>Skill 管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加 Skill</Button>
      </div>

      {gate && (
        <Alert style={{ marginBottom: 16 }} type={gate.passed ? 'success' : 'error'} showIcon
          message={gate.passed ? `安全检测通过（ID ${gate.id}）` : `安全检测未通过（ID ${gate.id}）`}
          description={<div>
            {gate.errors.map((e, i) => <div key={`e${i}`} style={{ color: 'var(--ice-danger)' }}>• {e}</div>)}
            {gate.warnings.map((w, i) => <div key={`w${i}`} style={{ color: 'var(--ice-warning, #faad14)' }}>• 建议：{w}</div>)}
            {gate.passed && gate.warnings.length === 0 && <div>未发现风险项。</div>}
          </div>}
          closable onClose={() => setGate(null)} />
      )}

      <Table columns={columns} dataSource={items} rowKey="id" loading={loading} pagination={false} />

      <Modal
        title={editing ? `编辑 Skill #${editing.id}` : '新建 Skill'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        width={720}
        styles={{ body: { maxHeight: '76vh', overflowY: 'auto' } }}
        footer={[
          <Button key="cancel" onClick={() => setModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => form.submit()}>保存</Button>,
        ]}
      >
        <Form form={form} layout="vertical" onFinish={handleSave} onFinishFailed={() => message.error('表单校验失败，请检查必填项')}>
          <Form.Item name="name" label="名称（唯一标识）" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="pdf-tool" disabled={!!editing} />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input placeholder="PDF 处理工具" /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={2} /></Form.Item>

          <Form.Item name="source_type" label="源类型" rules={[{ required: true }]}>
            <Select
              options={SOURCE_OPTIONS}
              optionRender={(option) => (
                <Space>
                  {option.data.icon}
                  <span>{option.data.label}</span>
                </Space>
              )}
            />
          </Form.Item>

          <Card
            size="small"
            style={{
              marginBottom: 16,
              borderLeft: `4px solid ${meta.accent}`,
              background: 'var(--ice-bg-secondary, rgba(255,255,255,0.04))',
              borderRadius: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              {SOURCE_OPTIONS.find(o => o.value === sourceType)?.icon}
              <Text strong style={{ color: 'var(--ice-text-primary)' }}>{meta.panelTitle}</Text>
            </div>
            <Text type="secondary" style={{ fontSize: 13 }}>{meta.panelDesc}</Text>
          </Card>

          {sourceType !== 'inline' && (
            <Form.Item
              name="path"
              label={meta.pathLabel}
              rules={[{ required: true, message: `请输入${meta.pathLabel}` }]}
              extra={meta.pathHelp}
            >
              <Input
                placeholder={meta.pathPlaceholder}
                prefix={sourceType === 'local' ? <FolderOutlined /> : sourceType === 'repo' ? <GithubOutlined /> : <GlobalOutlined />}
                suffix={
                  sourceType === 'remote' || sourceType === 'repo' ? (
                    <CopyOutlined
                      style={{ cursor: 'pointer', color: 'var(--ice-text-secondary)' }}
                      onClick={() => {
                        const p = form.getFieldValue('path') || ''
                        if (!p) return message.warning('没有可复制的内容')
                        navigator.clipboard.writeText(p).then(() => message.success('已复制')).catch(() => message.error('复制失败'))
                      }}
                    />
                  ) : undefined
                }
              />
            </Form.Item>
          )}

          <Form.Item
            name="content"
            label={meta.contentLabel}
            rules={[{ required: meta.contentRequired, message: '请填写内容' }]}
          >
            <Input.TextArea rows={meta.contentRows} placeholder={meta.contentPlaceholder} />
          </Form.Item>

          <Divider style={{ borderColor: 'var(--ice-border)' }} />

          <Form.Item name="trigger_words" label="触发词（模型据此判断何时加载）">
            <Select mode="tags" placeholder="pdf, 文档, 解析" tokenSeparators={[',']} />
          </Form.Item>
          <Form.Item name="declared_hooks" label="声明式 Hook（JSON，可选）" tooltip='启用技能时，这里声明的 Hook 会自动注册并激活。格式示例见下方占位符。'>
            <Input.TextArea rows={4} placeholder={'{\n  "PreToolUse": { "command": "echo {\'decision\':\'approve\'}" }\n}'} />
          </Form.Item>
          <Form.Item name="version" label="版本"><InputNumber min={1} max={999} style={{ width: 120 }} /></Form.Item>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}
