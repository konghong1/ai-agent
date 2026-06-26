import React, { useEffect, useState } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined, SettingOutlined, KeyOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, message } from 'antd'

import { authHeaders, authHeadersRaw } from '@/services/auth'

const { Title, Text } = Typography

export default function SettingsPage() {
  const [settings, setSettings] = useState<any[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()

  const fetch = async () => {
    try { const r = await fetch('/api/settings', { headers: authHeaders() }); setSettings(await r.json()) } catch {}
  }
  useEffect(() => { fetch() }, [])

  const handleSave = async (values: any) => {
    try {
      const url = editing ? `/api/settings/${editing.key}` : '/api/settings'
      const method = editing ? 'PATCH' : 'POST'
      const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(values) })
      if (res.ok) { message.success('保存成功'); setModalOpen(false); fetch() }
    } catch (e: any) { message.error(e.message) }
  }

  const handleDelete = (key: string) => {
    fetch(`/api/settings/${key}`, { method: 'DELETE', headers: authHeaders() }).then(() => fetch())
  }

  const columns = [
    { title: '键', dataIndex: 'key', key: 'key', width: 200, render: (t: string) => <Text style={{ color: '#00d4ff', fontFamily: 'monospace' }}>{t}</Text> },
    { title: '值', dataIndex: 'value', key: 'value', ellipsis: true, render: (t: string) => <Text style={{ color: '#e8f4f8' }}>{t}</Text> },
    { title: '描述', dataIndex: 'description', key: 'desc', ellipsis: true, render: (t: string) => <Text type="secondary">{t}</Text> },
    { title: '操作', key: 'action', width: 100,
      render: (_: any, r: any) => (
        <Space>
          <a onClick={() => { setEditing(r); form.setFieldsValue({ key: r.key, value: r.value, description: r.description }); setModalOpen(true) }}><EditOutlined /></a>
          <a onClick={() => handleDelete(r.key)} style={{ color: '#ff6b6b' }}><DeleteOutlined /></a>
        </Space>
      )}]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <Title level={4} style={{ color: '#e8f4f8', marginBottom: 16 }}>系统设置</Title>

      <Tabs items={[
        {
          key: 'global', label: '⚙ 全局配置',
          children: (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <Text type="secondary">管理系统全局键值配置</Text>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true) }}>添加设置</Button>
              </div>
              <Table columns={columns} dataSource={settings} rowKey="id" pagination={false} />
            </>
          )},
        {
          key: 'api', label: '🔑 API 配置',
          children: (
            <div style={{ maxWidth: 600 }}>
              <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>配置 OpenAI 兼容 API 的连接信息</Text>
              <Form layout="vertical">
                <Form.Item label="OpenAI API Key">
                  <Input.Password placeholder="sk-..." style={{ background: 'rgba(0, 212, 255, 0.04)', borderColor: 'rgba(0, 212, 255, 0.12)' }} />
                </Form.Item>
                <Form.Item label="OpenAI Base URL">
                  <Input placeholder="https://api.openai.com/v1" style={{ background: 'rgba(0, 212, 255, 0.04)', borderColor: 'rgba(0, 212, 255, 0.12)' }} />
                </Form.Item>
                <Form.Item label="默认模型">
                  <Input placeholder="gpt-4o-mini" style={{ background: 'rgba(0, 212, 255, 0.04)', borderColor: 'rgba(0, 212, 255, 0.12)' }} />
                </Form.Item>
                <Button type="primary" style={{ background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(0, 255, 213, 0.15))', borderColor: 'rgba(0, 212, 255, 0.4)' }}>保存 API 配置</Button>
              </Form>
            </div>
          )},
        {
          key: 'theme', label: '🎨 主题',
          children: (
            <div style={{ maxWidth: 400 }}>
              <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>选择界面主题风格</Text>
              {[
                { name: '冰晶默认', color: '#00d4ff', desc: '冰蓝色调，科技感' },
                { name: '深邃星空', color: '#7b68ee', desc: '紫色调，神秘感' },
                { name: '清新薄荷', color: '#00ffd5', desc: '绿色调，清爽感' }].map((t) => (
                <div key={t.name} style={{
                  display: 'flex', alignItems: 'center', gap: 16, padding: 16, marginBottom: 12,
                  borderRadius: 12, background: 'rgba(0, 212, 255, 0.04)',
                  border: `1px solid ${t.color}33`, cursor: 'pointer'}}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', background: t.color }} />
                  <div>
                    <Text strong style={{ color: '#e8f4f8' }}>{t.name}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>{t.desc}</Text>
                  </div>
                </div>
              ))}
            </div>
          )}]} />

      <Modal title={editing ? '编辑设置' : '添加设置'} open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} width={480}>
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="key" label="键" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="value" label="值" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input /></Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" style={{ marginRight: 8 }}>确定</Button>
            <Button onClick={() => setModalOpen(false)}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}




