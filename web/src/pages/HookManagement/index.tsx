import { useEffect, useState } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined, SafetyOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Tag, message, Alert, Popconfirm, InputNumber } from 'antd'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

const EVENTS = [
  { value: 'SessionStart', label: 'SessionStart（会话开始）' },
  { value: 'UserPromptSubmit', label: 'UserPromptSubmit（提交输入前）' },
  { value: 'PreToolUse', label: 'PreToolUse（工具调用前·可拦截）' },
  { value: 'PostToolUse', label: 'PostToolUse（工具调用后·可改写）' },
  { value: 'Stop', label: 'Stop（生成结束·可改写答案）' },
  { value: 'SubagentStop', label: 'SubagentStop' },
  { value: 'Notification', label: 'Notification' },
]

interface HookItem {
  id: number
  event: string
  matcher: string
  command: string
  env?: Record<string, string>
  secret_env?: string
  timeout_ms: number
  on_error: string
  enabled: boolean
}

function kvToObj(list: { key: string; value: string }[] | undefined): Record<string, string> {
  const o: Record<string, string> = {}
  ;(list || []).forEach((it) => { if (it.key) o[it.key] = it.value })
  return o
}

export default function HookManagement() {
  const [items, setItems] = useState<HookItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<HookItem | null>(null)
  const [gate, setGate] = useState<{ id: number; passed: boolean; errors: string[]; warnings: string[] } | null>(null)
  const [form] = Form.useForm()

  const fetchItems = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/hooks', { headers: authHeaders() })
      if (r.ok) { const data = await r.json(); setItems(Array.isArray(data) ? data : []) }
    } catch { /* */ } finally { setLoading(false) }
  }
  useEffect(() => { fetchItems() }, [])

  const openCreate = () => {
    setEditing(null); setGate(null); form.resetFields()
    form.setFieldsValue({ event: 'PreToolUse', matcher: '', on_error: 'block', enabled: false, timeout_ms: 30000, env: [] })
    setModalOpen(true)
  }
  const openEdit = (r: HookItem) => {
    setEditing(r); setGate(null); form.resetFields()
    const envList = Object.entries(r.env || {}).map(([key, value]) => ({ key, value }))
    form.setFieldsValue({ ...r, env: envList })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const v = await form.validateFields()
      const payload = {
        event: v.event, matcher: v.matcher || '', command: v.command,
        env: kvToObj(v.env), timeout_ms: v.timeout_ms, on_error: v.on_error, enabled: false,
      }
      const url = editing ? `/api/hooks/${editing.id}` : '/api/hooks'
      const res = await fetch(url, { method: editing ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(payload) })
      if (res.ok) { message.success('已保存，请先「安全检测」再「启用」'); setModalOpen(false); fetchItems() }
      else { const e = await res.json().catch(() => ({})); message.error(e.detail || e.message || '保存失败') }
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message || '保存失败') }
  }

  const runGate = async (r: HookItem) => {
    const res = await fetch(`/api/hooks/${r.id}/security-check`, { method: 'POST', headers: authHeaders() })
    const data = await res.json()
    setGate({ id: r.id, passed: !!data.passed, errors: data.errors || [], warnings: data.warnings || [] })
  }
  const handleEnable = async (r: HookItem) => {
    const res = await fetch(`/api/hooks/${r.id}/enable`, { method: 'POST', headers: authHeaders() })
    if (res.ok) { message.success('Hook 已启用并在生命周期中生效'); fetchItems() }
    else { const e = await res.json().catch(() => ({})); message.error((e.detail && e.detail.message) || e.message || '启用失败') }
  }
  const handleDelete = async (id: number) => { await fetch(`/api/hooks/${id}`, { method: 'DELETE', headers: authHeaders() }); fetchItems() }

  const columns = [
    { title: '事件', dataIndex: 'event', key: 'event', width: 150, render: (t: string) => <Tag color="purple">{t}</Tag> },
    { title: '匹配(glob)', dataIndex: 'matcher', key: 'matcher', render: (t: string) => <Text type="secondary" style={{ fontSize: 12 }}>{t || '（全部）'}</Text> },
    { title: '命令', dataIndex: 'command', key: 'cmd', ellipsis: true, render: (t: string) => <Text type="secondary" style={{ fontSize: 12 }}>{t}</Text> },
    { title: '失败策略', dataIndex: 'on_error', key: 'oe', width: 100, render: (t: string) => <Tag color={t === 'block' ? 'red' : 'orange'}>{t}</Tag> },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 90, render: (e: boolean) => e ? <Tag color="success">已启用</Tag> : <Tag>未启用</Tag> },
    {
      title: '操作', key: 'action', width: 220,
      render: (_: any, r: HookItem) => (
        <Space size="small">
          <a onClick={() => runGate(r)}><SafetyOutlined /> 检测</a>
          <a style={{ color: r.enabled ? 'var(--ice-text-secondary)' : 'var(--ice-primary)' }} onClick={() => handleEnable(r)}><CheckCircleOutlined /> 启用</a>
          <a onClick={() => openEdit(r)}><EditOutlined /></a>
          <Popconfirm title="确认删除该 Hook？" onConfirm={() => handleDelete(r.id)}>
            <a style={{ color: 'var(--ice-danger)' }}><DeleteOutlined /></a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>Hook 管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加 Hook</Button>
      </div>

      {gate && (
        <Alert style={{ marginBottom: 16 }} type={gate.passed ? 'success' : 'error'} showIcon
          message={gate.passed ? `安全检测通过（含沙箱试跑，ID ${gate.id}）` : `安全检测未通过（ID ${gate.id}）`}
          description={<div>
            {gate.errors.map((e, i) => <div key={`e${i}`} style={{ color: 'var(--ice-danger)' }}>• {e}</div>)}
            {gate.warnings.map((w, i) => <div key={`w${i}`} style={{ color: 'var(--ice-warning, #faad14)' }}>• 建议：{w}</div>)}
            {gate.passed && gate.warnings.length === 0 && <div>未发现风险项。</div>}
          </div>}
          closable onClose={() => setGate(null)} />
      )}

      <Table columns={columns} dataSource={items} rowKey="id" loading={loading} pagination={false} />

      <Modal
        title={editing ? `编辑 Hook #${editing.id}` : '新建 Hook'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        width={680}
        styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}
        footer={[
          <Button key="cancel" onClick={() => setModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => form.submit()}>保存</Button>,
        ]}
      >
        <Form form={form} layout="vertical" onFinish={handleSave} onFinishFailed={() => message.error('表单校验失败，请检查必填项')}>
          <Form.Item name="event" label="生命周期事件" rules={[{ required: true }]}>
            <Select options={EVENTS} />
          </Form.Item>
          <Form.Item name="matcher" label="工具名匹配（glob，如 mcp_*，留空=全部）">
            <Input placeholder="mcp_*" />
          </Form.Item>
          <Form.Item name="command" label="执行命令（stdin 收 JSON，stdout 输出决策 JSON）" tooltip="输出示例： { 'decision': 'approve' } 或 { 'decision': 'block', 'reason': '...' }" rules={[{ required: true, message: '请输入命令' }]}>
            <Input.TextArea rows={3} placeholder={'echo \'{"decision":"approve"}\''} />
          </Form.Item>
          <Form.Item label="非敏感环境变量">
            <Form.List name="env">
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...rest }) => (
                    <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                      <Form.Item {...rest} name={[name, 'key']} rules={[{ required: true, message: 'key' }]} style={{ marginBottom: 0 }}><Input placeholder="KEY" /></Form.Item>
                      <Form.Item {...rest} name={[name, 'value']} style={{ marginBottom: 0 }}><Input placeholder="value" /></Form.Item>
                      <DeleteOutlined onClick={() => remove(name)} />
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>添加变量</Button>
                </>
              )}
            </Form.List>
          </Form.Item>
          <Space size="large">
            <Form.Item name="on_error" label="失败策略">
              <Select options={[{ value: 'block', label: 'block（拦截，fail-closed）' }, { value: 'continue', label: 'continue（放行）' }]} />
            </Form.Item>
            <Form.Item name="timeout_ms" label="超时(ms)">
              <InputNumber min={500} max={600000} step={1000} style={{ width: 180 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}
