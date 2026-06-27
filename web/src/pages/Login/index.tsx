import { useState } from 'react'
import { Form, Input, Button, Tabs, Card, Typography, message } from 'antd'
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { ParticleBg } from '@/components/ParticleBg'
import './index.css'

const { Title, Text } = Typography

export default function Login() {
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (values: any) => {
    setLoading(true)
    setError('')
    try {
      if (values.mode === 'login') {
        await login(values.email, values.password)
        message.success('登录成功')
        navigate('/dashboard')
      } else {
        await register({ email: values.email, username: values.username, password: values.password })
        message.success('注册成功')
        navigate('/dashboard')
      }
    } catch (e: any) {
      setError(e.message || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <ParticleBg count={20} speed={0.15} opacity={0.2} />
      <Card className="login-card" bordered={false}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ color: '#00d4ff', marginBottom: 4 }}>AI Agent 管理平台</Title>
          <Text type="secondary">智能体 · 知识库 · 一体化管理</Text>
        </div>
        <Tabs defaultActiveKey="login" items={[
          { key: 'login', label: '登录', children: (
            <Form onFinish={handleSubmit} layout="vertical">
              <Form.Item name="mode" hidden initialValue="login" />
              <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
                <Input prefix={<MailOutlined />} placeholder="your@email.com" size="large" />
              </Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少 6 位' }]}>
                <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" size="large" />
              </Form.Item>
              {error && <Text type="danger" style={{ display: 'block', marginBottom: 8 }}>{error}</Text>}
              <Form.Item><Button type="primary" htmlType="submit" loading={loading} block size="large" className="login-btn">登录</Button></Form.Item>
            </Form>
          )},
          { key: 'register', label: '注册', children: (
            <Form onFinish={handleSubmit} layout="vertical">
              <Form.Item name="mode" hidden initialValue="register" />
              <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }, { min: 2, message: '至少 2 个字符' }]}>
                <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
              </Form.Item>
              <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
                <Input prefix={<MailOutlined />} placeholder="your@email.com" size="large" />
              </Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少 6 位' }]}>
                <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" size="large" />
              </Form.Item>
              {error && <Text type="danger" style={{ display: 'block', marginBottom: 8 }}>{error}</Text>}
              <Form.Item><Button type="primary" htmlType="submit" loading={loading} block size="large" className="login-btn">注册</Button></Form.Item>
            </Form>
          )},
        ]} />
      </Card>
    </div>
  )
}
