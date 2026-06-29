import { useEffect, useState } from 'react'
import { PlusOutlined, BookOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Modal, message, Tag, Row, Col, Switch } from 'antd'
import { useLayoutStore } from '@/stores/layout'
import { authHeaders } from '@/services/auth'

const { Title, Text } = Typography

interface KB {
  id: number; name: string; description: string; enabled: boolean
  chunk_size: number; chunk_overlap: number; embedding_model: string
  created_at: string
}

export default function KnowledgeBaseList() {
  const navigate = useNavigate()
  const theme = useLayoutStore((s) => s.theme)
  const [kbs, setKbs] = useState<KB[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<KB | null>(null)
  const [form] = Form.useForm()

  const themeColorMap: Record<string, string> = {
    techBlue: '#2563EB',
    naturalGreen: '#22C55E',
    elegantPurple: '#7C3AED',
  }
  const primaryColor = themeColorMap[theme] || '#22C55E'

  const fetchKbs = async () => {
    try {
      const res = await fetch('/api/knowledge-bases', { headers: authHeaders() })
      setKbs(await res.json())
    } catch {}
  }

  useEffect(() => { fetchKbs() }, [])

  const handleSave = async (values: any) => {
    setLoading(true)
    try {
      const url = editing ? `/api/knowledge-bases/${editing.id}` : '/api/knowledge-bases'
      const method = editing ? 'PATCH' : 'POST'
      const res = await fetch(url, {
        method, headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(values)})
      if (!res.ok) throw new Error('保存失败')
      message.success(editing ? '更新成功' : '创建成功')
      setModalOpen(false)
      setEditing(null)
      form.resetFields()
      fetchKbs()
    } catch (e: any) { message.error(e.message) }
    finally { setLoading(false) }
  }

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: '确认删除', content: '删除知识库会同时删除所有文档和向量数据',
      okText: '删除', okType: 'danger',
      onOk: async () => {
        const res = await fetch(`/api/knowledge-bases/${id}`, { method: 'DELETE', headers: authHeaders() })
        if (res.ok) { message.success('已删除'); fetchKbs() }
      }})
  }

  return (
    <div>
      <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <Title level={4} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>知识库管理</Title>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true) }}>
            新建知识库
          </Button>
        </div>

        {kbs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 48, color: 'var(--ice-text-muted)' }}>
            <BookOutlined style={{ fontSize: 48, opacity: 0.3 }} />
            <p style={{ marginTop: 12 }}>暂无知识库，点击"新建知识库"开始</p>
          </div>
        ) : (
          <Row gutter={[16, 16]}>
            {kbs.map((kb) => (
              <Col span={8} key={kb.id}>
                <IceCrystalCard hoverEffect="glow" animation="fadeInUp">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                    <div>
                      <Title level={5} style={{ color: 'var(--ice-text-primary)', margin: 0 }}>{kb.name}</Title>
                      <Text type="secondary" style={{ fontSize: 13 }}>{kb.description || '暂无描述'}</Text>
                    </div>
                    <Space>
                      <Button type="text" size="small" icon={<EditOutlined />} onClick={() => { setEditing(kb); form.setFieldsValue(kb); setModalOpen(true) }} />
                      <Button type="text" size="small" icon={<DeleteOutlined />} style={{ color: 'var(--ice-danger)' }} onClick={() => handleDelete(kb.id)} />
                    </Space>
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                    <Tag color="blue">{kb.embedding_model}</Tag>
                    <Tag>Chunk: {kb.chunk_size}</Tag>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Tag color={kb.enabled ? 'green' : 'red'}>{kb.enabled ? '已启用' : '已禁用'}</Tag>
                    <Button type="link" size="small" onClick={() => navigate(`/knowledge-bases/${kb.id}`)} style={{ color: primaryColor }}>
                      进入管理 →
                    </Button>
                  </div>
                </IceCrystalCard>
              </Col>
            ))}
          </Row>
        )}
      </IceCrystalCard>

      <Modal title={editing ? '编辑知识库' : '新建知识库'} open={modalOpen} onCancel={() => setModalOpen(false)}
        footer={null} width={560}>
        <Form form={form} layout="vertical" onFinish={handleSave} initialValues={{ chunk_size: 500, chunk_overlap: 50, enabled: true }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如: 产品文档" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="知识库描述" />
          </Form.Item>
          <Form.Item name="embedding_model" label="嵌入模型">
            <Input placeholder="text-embedding-3-small" />
          </Form.Item>
          <Form.Item name="chunk_size" label="分块大小">
            <Input type="number" min={100} max={4000} />
          </Form.Item>
          <Form.Item name="chunk_overlap" label="重叠大小">
            <Input type="number" min={0} max={500} />
          </Form.Item>
          <Form.Item name="enabled" valuePropName="checked" label="启用">
            <Switch />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={loading} style={{ marginRight: 8 }}>确定</Button>
            <Button onClick={() => setModalOpen(false)}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
