import { useEffect, useState } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined, SafetyOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Tag, message, Alert, Popconfirm, InputNumber } from 'antd'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

interface McpItem {
  id: number
  name: string
  transport: string
  url: string
  auth_type: string
  api_key?: string
  headers?: Record<string, string>
  tool_allowlist?: string[]
  timeout_ms?: number
  max_retries?: number
  enabled: boolean
  created_at?: string
}

function kvToObj(list: { key: string; value: string }[] | undefined): Record<string, string> {
  const o: Record<string, string> = {}
  ;(list || []).forEach((it) => { if (it.key) o[it.key] = it.value })
  return o
}

export default function MCPManagement() {
  const [items, setItems] = useState<McpItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<McpItem | null>(null)
  const [gate, setGate] = useState<{ id: number; passed: boolean; errors: string[]; warnings: string[] } | null>(null)
  const [form] = Form.useForm()

  const fetchItems = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/mcp-servers', { headers: authHeaders() })
      if (r.ok) {
        const data = await r.json()
        setItems(Array.isArray(data) ? data : [])
      }
    } catch { /* silent */ } finally { setLoading(false) }
  }
  useEffect(() => { fetchItems() }, [])

  const openCreate = () => {
    setEditing(null)
    setGate(null)
    form.resetFields()
    form.setFieldsValue({ transport: 'http', auth_type: 'none', enabled: false, timeout_ms: 30000, max_retries: 1, tool_allowlist: '' })
    setModalOpen(true)
  }

  const openEdit = (r: McpItem) => {
    setEditing(r)
    setGate(null)
    const headersList = Object.entries(r.headers || {}).map(([key, value]) => ({ key, value }))
    form.resetFields()
    form.setFieldsValue({
      ...r,
      headers: headersList,
      tool_allowlist: (r.tool_allowlist || []).join(', '),
    })
    setModalOpen(true)
  }

  const onFinishFailed = () => {
    message.error('表单校验失败，请检查必填项')
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const payload: any = {
        name: values.name,
        transport: values.transport,
        url: values.url,
        auth_type: values.auth_type,
        api_key: values.api_key || '',
        headers: kvToObj(values.headers),
        tool_allowlist: Array.isArray(values.tool_allowlist)
          ? values.tool_allowlist.map((s: any) => String(s).trim()).filter(Boolean)
          : String(values.tool_allowlist || '').split(',').map((s: string) => s.trim()).filter(Boolean),
        timeout_ms: values.timeout_ms,
        max_retries: values.max_retries,
        enabled: false, // 始终先经安全检测+启用流程
      }
      const url = editing ? `/api/mcp-servers/${editing.id}` : '/api/mcp-servers'
      const res = await fetch(url, {
        method: editing ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      })
      if (res.ok) { message.success('已保存，请先「安全检测」再「启用」'); setModalOpen(false); fetchItems() }
      else { const e = await res.json().catch(() => ({})); message.error(e.detail || e.message || '保存失败') }
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message || '保存失败') }
  }

  const runGate = async (r: McpItem) => {
    const res = await fetch(`/api/mcp-servers/${r.id}/security-check`, { method: 'POST', headers: authHeaders() })
    const data = await res.json()
    setGate({ id: r.id, passed: !!data.passed, errors: data.errors || [], warnings: data.warnings || [] })
  }

  const handleEnable = async (r: McpItem) => {
    const res = await fetch(`/api/mcp-servers/${r.id}/enable`, { method: 'POST', headers: authHeaders() })
    if (res.ok) { message.success('MCP 已启用并在聊天中可用'); fetchItems() }
    else {
      const e = await res.json().catch(() => ({}))
      message.error((e.detail && e.detail.message) || e.message || '启用失败（安全闸门未通过）')
    }
  }

  const handleDelete = async (id: number) => {
    await fetch(`/api/mcp-servers/${id}`, { method: 'DELETE', headers: authHeaders() })
    fetchItems()
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', render: (t: string) => <Text strong style={{ color: 'var(--ice-text-primary)' }}>{t}</Text> },
    { title: '传输', dataIndex: 'transport', key: 'transport', width: 90, render: (t: string) => <Tag color="cyan">{t}</Tag> },
    { title: 'URL', dataIndex: 'url', key: 'url', ellipsis: true, render: (t: string) => <Text type="secondary" style={{ fontSize: 12 }}>{t}</Text> },
    { title: '鉴权', dataIndex: 'auth_type', key: 'auth_type', width: 90, render: (t: string) => <Tag>{t}</Tag> },
    {
      title: '状态', dataIndex: 'enabled', key: 'enabled', width: 90,
      render: (e: boolean) => e
        ? <Tag color="success">已启用</Tag>
        : <Tag color="default">未启用</Tag>,
    },
    {
      title: '操作', key: 'action', width: 220,
      render: (_: any, r: McpItem) => (
        <Space size="small">
          <a onClick={() => runGate(r)}><SafetyOutlined /> 检测</a>
          <a style={{ color: r.enabled ? 'var(--ice-text-secondary)' : 'var(--ice-primary)' }} onClick={() => handleEnable(r)}>
            <CheckCircleOutlined /> 启用
          </a>
          <a onClick={() => openEdit(r)}><EditOutlined /></a>
          <Popconfirm title="确认删除该 MCP Server？" onConfirm={() => handleDelete(r.id)}>
            <a style={{ color: 'var(--ice-danger)' }}><DeleteOutlined /></a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>MCP Server 管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加 MCP</Button>
      </div>

      {gate && (
        <Alert
          style={{ marginBottom: 16 }}
          type={gate.passed ? 'success' : 'error'}
          showIcon
          message={gate.passed ? `安全检测通过（ID ${gate.id}）` : `安全检测未通过（ID ${gate.id}）`}
          description={
            <div>
              {gate.errors.map((e, i) => <div key={`e${i}`} style={{ color: 'var(--ice-danger)' }}>• {e}</div>)}
              {gate.warnings.map((w, i) => <div key={`w${i}`} style={{ color: 'var(--ice-warning, #faad14)' }}>• 建议：{w}</div>)}
              {gate.passed && gate.warnings.length === 0 && <div>未发现风险项。</div>}
            </div>
          }
          closable onClose={() => setGate(null)}
        />
      )}

      <Table columns={columns} dataSource={items} rowKey="id" loading={loading} pagination={false} />

      <Modal
        title={editing ? `编辑 MCP Server #${editing.id}` : '新建 MCP Server'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        width={620}
        styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}
        footer={[
          <Button key="cancel" onClick={() => setModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => form.submit()}>保存</Button>,
        ]}
      >
        <Form form={form} layout="vertical" onFinish={handleSave} onFinishFailed={onFinishFailed}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="my-remote-mcp" />
          </Form.Item>
          <Form.Item name="transport" label="传输方式" rules={[{ required: true }]}>
            <Select options={[{ value: 'http', label: 'Streamable-HTTP' }, { value: 'sse', label: 'SSE' }]} />
          </Form.Item>
          <Form.Item name="url" label="服务地址" rules={[{ required: true, message: '请输入 URL' }]}>
            <Input placeholder="https://api.example.com/mcp" />
          </Form.Item>
          <Form.Item name="auth_type" label="鉴权方式">
            <Select options={[
              { value: 'none', label: '无' },
              { value: 'bearer', label: 'Bearer Token' },
              { value: 'api_key', label: 'API Key (X-API-Key)' },
            ]} />
          </Form.Item>
          <Form.Item noStyle dependencies={['auth_type']}>
            {({ getFieldValue }) => getFieldValue('auth_type') !== 'none' ? (
              <Form.Item name="api_key" label="密钥（加密存储）" rules={[{ required: true, message: '请填写密钥' }]}>
                <Input.Password placeholder="sk-..." />
              </Form.Item>
            ) : null}
          </Form.Item>

          <Form.Item label="自定义请求头（Headers）">
            <Form.List name="headers">
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...rest }) => (
                    <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                      <Form.Item {...rest} name={[name, 'key']} rules={[{ required: true, message: 'key' }]} style={{ marginBottom: 0 }}>
                        <Input placeholder="Header-Name" />
                      </Form.Item>
                      <Form.Item {...rest} name={[name, 'value']} style={{ marginBottom: 0 }}>
                        <Input placeholder="value" />
                      </Form.Item>
                      <DeleteOutlined onClick={() => remove(name)} />
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>添加 Header</Button>
                </>
              )}
            </Form.List>
          </Form.Item>

          <Form.Item name="tool_allowlist" label="工具白名单（逗号分隔，留空=全部）">
            <Input placeholder="tool_a, tool_b" />
          </Form.Item>
          <Space size="large">
            <Form.Item name="timeout_ms" label="超时(ms)">
              <InputNumber min={1000} max={300000} step={1000} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="max_retries" label="最大重试">
              <InputNumber min={0} max={5} style={{ width: 120 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}
