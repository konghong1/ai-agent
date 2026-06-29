import { useEffect, useState } from 'react'
import { PlusOutlined, EditOutlined, DeleteOutlined, SettingOutlined, KeyOutlined, SunOutlined, MoonOutlined } from '@ant-design/icons'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { Typography, Form, Input, Button, Space, Table, Modal, message, Tabs, Switch } from 'antd'
import { authHeaders, authHeadersRaw } from '@/services/auth'
import { useLayoutStore } from '@/stores/layout'

const { Title, Text } = Typography

export default function SettingsPage() {
  const [settings, setSettings] = useState<any[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()
  const { darkMode, toggleDarkMode, theme, setTheme } = useLayoutStore()

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
    { title: '键', dataIndex: 'key', key: 'key', width: 200, render: (t: string) => <Text style={{ color: 'var(--ice-primary)', fontFamily: 'monospace' }}>{t}</Text> },
    { title: '值', dataIndex: 'value', key: 'value', ellipsis: true, render: (t: string) => <Text style={{ color: 'var(--ice-text-primary)' }}>{t}</Text> },
    { title: '描述', dataIndex: 'description', key: 'desc', ellipsis: true, render: (t: string) => <Text type="secondary">{t}</Text> },
    { title: '操作', key: 'action', width: 100,
      render: (_: any, r: any) => (
        <Space>
          <a onClick={() => { setEditing(r); form.setFieldsValue({ key: r.key, value: r.value, description: r.description }); setModalOpen(true) }}><EditOutlined /></a>
          <a onClick={() => handleDelete(r.key)} style={{ color: 'var(--ice-danger)' }}><DeleteOutlined /></a>
        </Space>
      )}]

  const themeOptions = [
    { name: '自然绿', key: 'naturalGreen', color: '#22C55E', desc: '护眼舒适，适合长时间办公' },
    { name: '科技蓝', key: 'techBlue', color: '#2563EB', desc: '专业稳重，适合企业后台' },
    { name: '优雅紫', key: 'elegantPurple', color: '#7C3AED', desc: 'AI 科技高级风' },
  ]

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <Title level={4} style={{ color: 'var(--ice-text-primary)', marginBottom: 16 }}>系统设置</Title>

      <Tabs items={[
        {
          key: 'global', label: <><SettingOutlined /> 全局配置</>,
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
          key: 'api', label: <><KeyOutlined /> API 配置</>,
          children: (
            <div style={{ maxWidth: 600 }}>
              <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>配置 OpenAI 兼容 API 的连接信息</Text>
              <Form layout="vertical">
                <Form.Item label="OpenAI API Key">
                  <Input.Password placeholder="sk-..." style={{ background: 'var(--ice-bg-card)', borderColor: 'var(--ice-border)' }} />
                </Form.Item>
                <Form.Item label="OpenAI Base URL">
                  <Input placeholder="https://api.openai.com/v1" style={{ background: 'var(--ice-bg-card)', borderColor: 'var(--ice-border)' }} />
                </Form.Item>
                <Form.Item label="默认模型">
                  <Input placeholder="gpt-4o-mini" style={{ background: 'var(--ice-bg-card)', borderColor: 'var(--ice-border)' }} />
                </Form.Item>
                <Button type="primary" style={{ background: 'var(--ice-primary)', borderColor: 'var(--ice-primary)' }}>保存 API 配置</Button>
              </Form>
            </div>
          )},
        {
          key: 'theme', label: '🎨 主题',
          children: (
            <div style={{ maxWidth: 500 }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: 16, marginBottom: 20, borderRadius: 12,
                background: 'var(--ice-bg-card)', border: '1px solid var(--ice-border)',
              }}>
                <div>
                  <Text strong style={{ color: 'var(--ice-text-primary)', display: 'block' }}>深色 / 浅色模式</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>切换界面明暗风格</Text>
                </div>
                <Switch checked={darkMode} onChange={toggleDarkMode}
                  checkedChildren={<MoonOutlined />} unCheckedChildren={<SunOutlined />} />
              </div>

              <Text strong style={{ color: 'var(--ice-text-primary)', display: 'block', marginBottom: 12 }}>选择主题风格</Text>
              {themeOptions.map((t) => {
                const isActive = theme === t.key
                return (
                  <div
                    key={t.key}
                    onClick={() => { setTheme(t.key); message.success('主题已切换: ' + t.name) }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 16, padding: 16, marginBottom: 12,
                      borderRadius: 12,
                      background: isActive ? t.color + '18' : 'var(--ice-bg-card)',
                      border: '1px solid ' + (isActive ? t.color + '88' : 'var(--ice-border)'),
                      cursor: 'pointer',
                      boxShadow: isActive ? '0 0 20px ' + t.color + '22' : 'none',
                    }}
                  >
                    <div style={{
                      width: 40, height: 40, borderRadius: '50%',
                      background: t.color,
                      boxShadow: '0 0 12px ' + t.color + '44',
                      border: isActive ? '3px solid var(--ice-text-primary)' : '3px solid transparent',
                    }} />
                    <div>
                      <Text strong style={{ color: isActive ? t.color : 'var(--ice-text-primary)' }}>{t.name}</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>{t.desc}</Text>
                    </div>
                    {isActive && <Text style={{ color: t.color, fontSize: 13, fontWeight: 600 }}>✓ 当前</Text>}
                  </div>
                )
              })}
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
