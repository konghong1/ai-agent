import { useEffect, useState } from 'react'
import {
  Tabs, Table, Button, Form, Input, Select, InputNumber, Tag, Space,
  Typography, Card, Empty, App, Modal,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, EditOutlined, CheckOutlined, CloseOutlined,
} from '@ant-design/icons'
import { memoryApi, MemoryItem, PendingItem, MemoryPreview } from '@/services/memory'

const { Title, Text, Paragraph } = Typography

const LAYER_COLORS = ['gold', 'blue', 'green', 'purple']
const LAYER_LABELS = ['L0 核心身份', 'L1 显式记忆', 'L2 派生', 'L3 会话沉淀']

function fmtTime(v?: string | null): string {
  if (!v) return '-'
  const iso = v.endsWith('Z') || v.includes('+') ? v : v + 'Z'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? v : d.toLocaleString()
}

export default function MemoryPanel() {
  const { message, modal } = App.useApp()
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [pending, setPending] = useState<PendingItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<MemoryItem | null>(null)
  const [form] = Form.useForm()

  const [previewText, setPreviewText] = useState('')
  const [preview, setPreview] = useState<MemoryPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [m, p] = await Promise.all([memoryApi.list(), memoryApi.listPending()])
      setMemories(m || [])
      setPending(p || [])
    } catch {
      // request() 已弹错误 toast
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ layer: 1, mem_type: 'preference', importance: 0.5, confidence: 1.0 })
    setModalOpen(true)
  }
  const openEdit = (m: MemoryItem) => {
    setEditing(m)
    form.setFieldsValue(m)
    setModalOpen(true)
  }

  const submit = async () => {
    const vals = await form.validateFields()
    try {
      if (editing) {
        await memoryApi.update(editing.id, vals)
        message.success('已更新记忆')
      } else {
        await memoryApi.create(vals)
        message.success('已写入记忆')
      }
      setModalOpen(false)
      load()
    } catch {
      // request() 已弹错误 toast
    }
  }

  const doDelete = (m: MemoryItem) => {
    modal.confirm({
      title: '软删除该记忆？',
      content: '将标记为 archived（可恢复），不会物理删除。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await memoryApi.remove(m.id)
        message.success('已软删除')
        load()
      },
    })
  }

  const accept = async (id: number) => {
    try { await memoryApi.acceptPending(id) } catch { return }
    load() // 无条件先刷新列表（核心反馈），toast 失败不影响列表更新
    try { message.success('已接受为长期记忆') } catch { /* toast 失败不影响列表 */ }
  }
  const reject = async (id: number) => {
    try { await memoryApi.rejectPending(id) } catch { return }
    load()
    try { message.success('已拒绝') } catch { /* toast 失败不影响列表 */ }
  }

  const runPreview = async () => {
    setPreviewLoading(true)
    try {
      const r = await memoryApi.preview(previewText)
      setPreview(r)
    } catch {
      // request() 已弹错误 toast
    } finally {
      setPreviewLoading(false)
    }
  }

  const memColumns = [
    {
      title: '层级', dataIndex: 'layer', width: 120,
      render: (l: number) => <Tag color={LAYER_COLORS[l] || 'default'}>{LAYER_LABELS[l] || `L${l}`}</Tag>,
    },
    { title: '类型', dataIndex: 'mem_type', width: 100, render: (t: string) => <Tag>{t}</Tag> },
    { title: '键', dataIndex: 'key', width: 160, ellipsis: true },
    { title: '值', dataIndex: 'value', ellipsis: true },
    { title: '重要度', dataIndex: 'importance', width: 90, render: (v: number) => (v == null ? '-' : v.toFixed(2)) },
    {
      title: '操作', width: 140,
      render: (_: unknown, r: MemoryItem) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => doDelete(r)} data-testid="mem-del-row">删除</Button>
        </Space>
      ),
    },
  ]

  const pendingColumns = [
    { title: '候选内容', dataIndex: 'candidate', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: (v: string) => fmtTime(v) },
    {
      title: '操作', width: 150,
      render: (_: unknown, r: PendingItem) => (
        <Space>
          <Button size="small" type="primary" icon={<CheckOutlined />} data-testid={`accept-${r.id}`} onClick={() => accept(r.id)}>接受</Button>
          <Button size="small" danger icon={<CloseOutlined />} data-testid={`reject-${r.id}`} onClick={() => reject(r.id)}>拒绝</Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>长期记忆</Title>
          <Text type="secondary">
            跨会话保存的用户偏好、事实与实体（软删除可恢复）。这是注入对话上下文的优先路径。
          </Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-testid="mem-new">新建记忆</Button>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Title level={5} style={{ marginTop: 0 }}>诊断预览（上下文注入检查）</Title>
        <Text type="secondary">
          输入一句话，查看记忆系统会向上下文注入哪些块（Reflex 指针 + 语义回忆 + 核心记忆）。无需 LLM。
        </Text>
        <Input.TextArea
          rows={2}
          value={previewText}
          onChange={(e) => setPreviewText(e.target.value)}
          placeholder="例如：我更喜欢用简体中文交流"
          style={{ margin: '12px 0' }}
        />
        <Button onClick={runPreview} loading={previewLoading} data-testid="mem-preview">生成预览</Button>
        {preview && (
          <div style={{ marginTop: 16 }}>
            {(() => {
              const entries = Object.entries(preview).filter(([, t]) => t && String(t).trim())
              const totalChars = entries.reduce((s, [, t]) => s + String(t).length, 0)
              const estTokens = Math.ceil(totalChars / 4)
              return (
                <>
                  <Tag color="blue">估算 tokens（约）: {estTokens}</Tag>
                  {entries.length === 0
                    ? <Empty description="无注入块（提示：在系统设置中开启 Retrieval Reflex / 语义回忆后才会注入记忆块）" />
                    : entries.map(([label, text]) => (
                      <div key={label} style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 12, marginBottom: 8 }}>
                        <Tag color="geekblue">{label}</Tag>
                        <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }}>{text}</Paragraph>
                      </div>
                    ))}
                </>
              )
            })()}
          </div>
        )}
      </Card>

      <Tabs
        items={[
          {
            key: 'mem',
            label: `显式记忆 (${memories.length})`,
            children: (
              <Table
                rowKey="id"
                loading={loading}
                columns={memColumns}
                dataSource={memories}
                pagination={false}
                locale={{ emptyText: <Empty description="还没有长期记忆，点右上角新建" /> }}
              />
            ),
          },
          {
            key: 'pending',
            label: `待确认候选 (${pending.length})`,
            children: (
              pending.length === 0
                ? <Empty description="暂无隐式提取候选（开启隐式提取后，模型会从对话中建议记忆）" />
                : <Table rowKey="id" columns={pendingColumns} dataSource={pending} pagination={false} />
            ),
          },
        ]}
      />

      <Modal
        title={editing ? '编辑记忆' : '新建记忆'}
        open={modalOpen}
        onOk={submit}
        onCancel={() => setModalOpen(false)}
        okText="保存"
        cancelText="取消"
        okButtonProps={{ 'data-testid': 'mem-save' }}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="key" label="键（实体 / 主题）" rules={[{ required: true, message: '请输入键' }]}>
            <Input placeholder="如：语言偏好" />
          </Form.Item>
          <Form.Item name="value" label="值" rules={[{ required: true, message: '请输入值' }]}>
            <Input.TextArea rows={2} placeholder="如：用户偏好使用简体中文" />
          </Form.Item>
          <Space size="large" style={{ display: 'flex' }}>
            <Form.Item name="layer" label="层级" rules={[{ required: true }]}>
              <Select
                style={{ width: 160 }}
                options={LAYER_LABELS.map((l, i) => ({ value: i, label: l }))}
              />
            </Form.Item>
            <Form.Item name="mem_type" label="类型" rules={[{ required: true }]}>
              <Select
                style={{ width: 160 }}
                options={[
                  { value: 'preference', label: '偏好' },
                  { value: 'fact', label: '事实' },
                  { value: 'project', label: '项目' },
                  { value: 'person', label: '人物' },
                  { value: 'entity', label: '实体' },
                  { value: 'other', label: '其他' },
                ]}
              />
            </Form.Item>
          </Space>
          <Space size="large" style={{ display: 'flex' }}>
            <Form.Item name="importance" label="重要度 (0-1)" rules={[{ required: true }]}>
              <InputNumber min={0} max={1} step={0.1} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="confidence" label="置信度 (0-1)" rules={[{ required: true }]}>
              <InputNumber min={0} max={1} step={0.1} style={{ width: 160 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  )
}
