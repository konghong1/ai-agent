import { useCallback, useEffect, useState } from 'react'
import { Table, Tag, Switch, Button, Space, Modal, Form, Input, Select, message, Typography, Tooltip } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { useLayoutStore } from '@/stores/layout'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

interface PromptTemplate {
  id: number
  name: string
  description: string
  system_prompt: string
  slug: string
  variables: string[]
  category: string
  enabled: boolean
  is_default: boolean
  created_at: string
  updated_at: string
}

const CATEGORIES = [
  { value: 'general', label: '通用' },
  { value: 'coding', label: '编程' },
  { value: 'analysis', label: '数据分析' },
  { value: 'writing', label: '写作' },
  { value: 'translation', label: '翻译' },
  { value: 'custom', label: '自定义' },
]

export default function PromptTemplateList() {
  const navigate = useNavigate()
  const theme = useLayoutStore((s) => s.theme)
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<PromptTemplate | null>(null)
  const [form] = Form.useForm()

  const themeColorMap: Record<string, string> = {
    techBlue: '#2563EB',
    naturalGreen: '#22C55E',
    elegantPurple: '#7C3AED',
  }
  const primaryColor = themeColorMap[theme] || '#22C55E'

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await fetch('/api/prompt-templates', { headers: authHeaders() })
      if (!res.ok) { setTemplates([]); return }
      setTemplates(await res.json())
    } catch {}
  }, [])

  useEffect(() => { fetchTemplates() }, [fetchTemplates])

  const handleSave = async (values: any) => {
    setLoading(true)
    try {
      const url = editing ? `/api/prompt-templates/${editing.id}` : '/api/prompt-templates'
      const method = editing ? 'PATCH' : 'POST'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(values),
      })
      if (!res.ok) throw new Error('保存失败')
      message.success(editing ? '更新成功' : '创建成功')
      setDrawerOpen(false)
      setEditing(null)
      form.resetFields()
      fetchTemplates()
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: '确认删除',
      content: '删除后无法恢复',
      okText: '删除',
      okType: 'danger',
      onOk: async () => {
        const r = await fetch(`/api/prompt-templates/${id}`, { method: 'DELETE', headers: authHeaders() })
        if (r.ok) { message.success('已删除'); fetchTemplates() }
      },
    })
  }

  const handleToggle = async (id: number, checked: boolean) => {
    await fetch(`/api/prompt-templates/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ enabled: checked }),
    })
    fetchTemplates()
  }

  const getCategoryColor = (cat: string) => {
    const colors: Record<string, string> = {
      general: 'default',
      coding: 'blue',
      analysis: 'purple',
      writing: 'green',
      translation: 'orange',
      custom: 'cyan',
    }
    return colors[cat] || 'default'
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
      render: (name: string, r: PromptTemplate) => (
        <a onClick={() => { setEditing(r); form.setFieldsValue(r); setDrawerOpen(true) }} style={{ color: primaryColor }}>
          {name}
        </a>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (cat: string) => <Tag color={getCategoryColor(cat)}>{cat}</Tag>,
    },
    {
      title: '系统提示词摘要',
      dataIndex: 'system_prompt',
      key: 'system_prompt',
      ellipsis: true,
      render: (text: string) => text && text.length > 40 ? <Tooltip title={text}>{text.slice(0, 40)}...</Tooltip> : text,
    },
    {
      title: '变量',
      dataIndex: 'variables',
      key: 'variables',
      width: 80,
      render: (vars: string[]) => vars && vars.length > 0 ? <Tag>{vars.length}</Tag> : '-',
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (e: boolean, r: PromptTemplate) => (
        <Switch checked={e} onChange={(v) => handleToggle(r.id, v)} size="small" />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right' as const,
      render: (_: any, r: PromptTemplate) => (
        <Space>
          <a onClick={() => { setEditing(r); form.setFieldsValue(r); setDrawerOpen(true) }}>
            <EditOutlined />
          </a>
          <a onClick={() => handleDelete(r.id)} style={{ color: 'var(--ice-danger)' }}>
            <DeleteOutlined />
          </a>
        </Space>
      ),
    },
  ]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>提示词模板管理</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>管理可复用的系统提示词模板，在聊天时选择使用</Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => {
          setEditing(null)
          form.setFieldsValue({ enabled: true, is_default: false, variables: [] })
          setDrawerOpen(true)
        }}>
          新建模板
        </Button>
      </div>
      <Table columns={columns} dataSource={templates} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} scroll={{ x: 800 }} />

      <Modal
        title={editing ? '编辑模板' : '新建模板'}
        open={drawerOpen}
        onCancel={() => { setDrawerOpen(false); setEditing(null) }}
        footer={null}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSave} initialValues={{ category: 'general', enabled: true, is_default: false }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如: 代码审查助手" />
          </Form.Item>
          <Form.Item name="slug" label="唯一标识" rules={[{ required: true, message: '请输入slug' }]}>
            <Input placeholder="例如: code_review (英文字符和下划线)" />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Select options={CATEGORIES} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="简短描述用途" />
          </Form.Item>
          <Form.Item name="system_prompt" label="系统提示词" rules={[{ required: true, message: '请输入系统提示词' }]}>
            <Input.TextArea rows={6} placeholder="Agent 的系统指令... 可使用 {{variable}} 作为变量占位符" />
          </Form.Item>
          <Form.Item name="variables" label="模板变量">
            <Input placeholder="逗号分隔，如: context,languages (可选)" />
          </Form.Item>
          <Form.Item name="is_default" valuePropName="checked" label="设为默认">
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
          <Form.Item name="enabled" valuePropName="checked" label="启用">
            <Switch />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={loading} style={{ marginRight: 8 }}>确定</Button>
            <Button onClick={() => { setDrawerOpen(false); setEditing(null) }}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}
