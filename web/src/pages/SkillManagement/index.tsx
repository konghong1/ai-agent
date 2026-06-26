import React, { useEffect, useState } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Switch, Tag, message } from 'antd'

import { authHeaders, authHeadersRaw } from '@/services/auth'

const { Title, Text } = Typography

export default function SkillManagement() {
  const [items, setItems] = useState<any[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()

  const fetch = async () => {
    try { const r = await fetch('/api/skills', { headers: authHeaders() }); setItems(await r.json()) } catch {}
  }
  useEffect(() => { fetch() }, [])

  const handleSave = async (values: any) => {
    try {
      const url = editing ? `/api/skills/${editing.id}` : '/api/skills'
      const res = await fetch(url, { method: editing ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(values) })
      if (res.ok) { message.success('保存成功'); setModalOpen(false); fetch() }
    } catch (e: any) { message.error(e.message) }
  }

  const handleDelete = (id: number) => {
    fetch(`/api/skills/${id}`, { method: 'DELETE', headers: authHeaders() }).then(() => fetch())
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', render: (t: string) => <Text strong style={{ color: '#e8f4f8' }}>{t}</Text> },
    { title: '标题', dataIndex: 'title', key: 'title', render: (t: string) => <Text style={{ color: '#8899aa' }}>{t}</Text> },
    { title: '类型', dataIndex: 'source_type', key: 'type', width: 100, render: (t: string) => <Tag>{t}</Tag> },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80,
      render: (e: boolean, r: any) => <Switch checked={e} onChange={(v) => fetch(`/api/skills/${r.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ enabled: v }) })} size="small" /> },
    { title: '操作', key: 'action', width: 100,
      render: (_: any, r: any) => (
        <Space>
          <a onClick={() => { setEditing(r); form.setFieldsValue(r); setModalOpen(true) }}><EditOutlined /></a>
          <a onClick={() => handleDelete(r.id)} style={{ color: '#ff6b6b' }}><DeleteOutlined /></a>
        </Space>
      )}]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: '#e8f4f8', margin: 0 }}>Skill 管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields({ source_type: 'local', enabled: true }); setModalOpen(true) }}>添加 Skill</Button>
      </div>
      <Table columns={columns} dataSource={items} rowKey="id" pagination={false} />

      <Modal title={editing ? '编辑 Skill' : '新建 Skill'} open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} width={520}>
        <Form form={form} layout="vertical" onFinish={handleSave} initialValues={{ source_type: 'local', enabled: true }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="source_type" label="源类型">
            <Select options={[{ value: 'local', label: '本地' }, { value: 'remote', label: '远程' }]} />
          </Form.Item>
          <Form.Item name="path" label="路径"><Input /></Form.Item>
          <Form.Item name="enabled" valuePropName="checked" label="启用"><Switch /></Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" style={{ marginRight: 8 }}>确定</Button>
            <Button onClick={() => setModalOpen(false)}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}




