import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Typography, Space, Input, Button, message, Spin, Dropdown, Modal, Form, Tag } from 'antd'
import {
  SendOutlined, PlusOutlined, DeleteOutlined, ReloadOutlined,
  DownOutlined, RobotOutlined, UserOutlined,
  MoreOutlined, FolderOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useLayoutStore } from '@/stores/layout'
import { authHeaders } from '@/services/auth'

const { Text, Title } = Typography
const { TextArea } = Input

interface Agent {
  id: number; name: string; description: string; system_prompt: string
  model_provider: string; model_name: string; temperature: number; enabled: boolean
}

interface Thread {
  id: string
  title: string
  agent_id: number
  created_at: string
  updated_at: string
}

interface Message {
  id: number
  role: string
  content: string
  created_at: string
}

export default function AgentChat() {
  const navigate = useNavigate()
  const theme = useLayoutStore((s) => s.theme)
  const [agents, setAgents] = useState<Agent[]>([])
  const [activeAgentId, setActiveAgentId] = useState<number | null>(null)
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [showNewThreadModal, setShowNewThreadModal] = useState(false)
  const [newThreadTitle, setNewThreadTitle] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const themeColorMap: Record<string, string> = {
    techBlue: '#2563EB',
    naturalGreen: '#22C55E',
    elegantPurple: '#7C3AED',
  }
  const primaryColor = themeColorMap[theme] || '#22C55E'
  const accentColor = theme === 'techBlue' ? '#60A5FA' : theme === 'naturalGreen' ? '#86EFAC' : '#A78BFA'

  useEffect(() => {
    fetch('/api/agents', { headers: authHeaders() })
      .then(r => r.json())
      .then(setAgents)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (agents.length > 0 && !activeAgentId) setActiveAgentId(agents[0].id)
  }, [agents, activeAgentId])

  useEffect(() => {
    if (!activeAgentId) return
    fetch(`/api/agents/${activeAgentId}/threads`, { headers: authHeaders() })
      .then(r => r.json()).then(setThreads).catch(() => {})
  }, [activeAgentId])

  useEffect(() => {
    if (!activeThreadId) { setMessages([]); return }
    fetch(`/api/threads/${activeThreadId}/messages`, { headers: authHeaders() })
      .then(r => r.json()).then(setMessages).catch(() => setMessages([]))
  }, [activeThreadId])

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const activeAgent = agents.find(a => a.id === activeAgentId) || null

  // 新建会话
  const createThread = async () => {
    if (!activeAgentId) { message.warning('请先选择一个 Agent'); return }
    const title = newThreadTitle.trim() || '新会话'
    try {
      const res = await fetch(`/api/agents/${activeAgentId}/threads`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ agent_id: activeAgentId, title }),
      })
      if (res.ok) {
        const data = await res.json()
        setThreads(prev => [data, ...prev])
        setActiveThreadId(data.id)
        setShowNewThreadModal(false)
        setNewThreadTitle('')
        message.success('会话已创建')
      } else {
        const err = await res.json().catch(() => ({}))
        message.error(err.detail || '创建失败')
      }
    } catch (e: any) { message.error(e.message || '创建失败') }
  }

  // 删除会话
  const deleteThread = async (threadId: string) => {
    try {
      const res = await fetch(`/api/threads/${threadId}`, { method: 'DELETE', headers: authHeaders() })
      if (res.ok || res.status === 204) {
        setThreads(prev => prev.filter(t => t.id !== threadId))
        if (activeThreadId === threadId) { setActiveThreadId(null); setMessages([]) }
        message.success('会话已删除')
      } else {
        message.error('删除失败')
      }
    } catch (e: any) { message.error(e.message || '删除失败') }
  }

  // 刷新消息
  const refreshMessages = async () => {
    if (!activeThreadId) return
    try {
      const res = await fetch(`/api/threads/${activeThreadId}/messages`, { headers: authHeaders() })
      const data = await res.json(); setMessages(data); message.success('已刷新')
    } catch (e: any) { message.error('刷新失败') }
  }

  // 发送消息（自动创建会话如果还没选）
  const handleSend = async () => {
    if (!input.trim() || sending || !activeAgentId) return
    setSending(true)
    const userMsg: Message = { id: Date.now(), role: 'user', content: input, created_at: new Date().toISOString() }
    setMessages(prev => [...prev, userMsg]); setInput('')

    try {
      const res = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          agent_id: activeAgentId,
          message: userMsg.content,
          thread_id: activeThreadId || undefined,
        }),
      })
      const data = await res.json()
      const assistantMsg: Message = { id: Date.now() + 1, role: 'assistant', content: data.answer, created_at: new Date().toISOString() }
      setMessages(prev => [...prev, assistantMsg])
      // 如果是新会话，后端会返回 thread_id
      if (data.thread_id) {
        setActiveThreadId(data.thread_id)
        // 更新线程列表中的标题
        setThreads(prev => {
          const existing = prev.find(t => t.id === data.thread_id)
          if (existing) return prev
          const newThread: Thread = {
            id: data.thread_id,
            title: data.thread_title || userMsg.content.substring(0, 40) || '新会话',
            agent_id: activeAgentId!,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }
          return [newThread, ...prev]
        })
      }
    } catch (e: any) {
      message.error(e.message || '发送失败')
      setMessages(prev => prev.filter(m => m.id !== userMsg.id))
    } finally { setSending(false) }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  // 线程菜单
  const threadMenuItems = (thread: Thread) => [{
    key: 'delete', icon: <DeleteOutlined style={{ color: 'var(--ice-danger)' }} />,
    label: '删除会话', danger: true, onClick: () => deleteThread(thread.id),
  }]

  // Agent 选择菜单
  const agentMenuItems = agents.map(agent => ({
    key: String(agent.id),
    label: <Space><RobotOutlined style={{ color: agent.id === activeAgentId ? primaryColor : 'var(--ice-text-muted)' }} /><Text style={{ color: 'var(--ice-text-primary)' }}>{agent.name}</Text></Space>,
    onClick: () => { setActiveAgentId(agent.id); setActiveThreadId(null) },
  }))

  if (loading) return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spin size="large" /></div>

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--ice-bg-primary)', overflow: 'hidden' }}>
      {/* 左侧边栏 - 会话列表 */}
      <div style={{ width: 280, minWidth: 280, background: 'var(--ice-bg-secondary)', borderRight: '1px solid var(--ice-border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* 头部：Agent 选择 + 新建 */}
        <div style={{ padding: '16px', borderBottom: '1px solid var(--ice-border)' }}>
          <div style={{ marginBottom: 12 }}>
            <Dropdown menu={{ items: agentMenuItems }} placement="bottomLeft" arrow>
              <Button type="text" block style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: 'var(--ice-text-primary)', fontWeight: 600 }}>
                <Space><RobotOutlined style={{ color: primaryColor, fontSize: 18 }} /><Text>{activeAgent?.name || '选择 Agent'}</Text></Space>
                <DownOutlined style={{ fontSize: 12, color: 'var(--ice-text-secondary)' }} />
              </Button>
            </Dropdown>
          </div>
          <Button type="primary" icon={<PlusOutlined />} block onClick={() => setShowNewThreadModal(true)} style={{ background: primaryColor, borderColor: primaryColor }}>新建会话</Button>
        </div>

        {/* 会话列表 */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
          {threads.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--ice-text-muted)' }}>
              <FolderOutlined style={{ fontSize: 32, opacity: 0.3, display: 'block', marginBottom: 8 }} />
              <Text type="secondary" style={{ fontSize: 13 }}>暂无会话</Text>
            </div>
          ) : threads.map(thread => (
            <div key={thread.id} onClick={() => setActiveThreadId(thread.id)}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', marginBottom: 4, borderRadius: 8, cursor: 'pointer',
                background: activeThreadId === thread.id ? 'var(--ice-primary-10)' : 'transparent',
                border: activeThreadId === thread.id ? `1px solid ${primaryColor}33` : '1px solid transparent', transition: 'all 0.2s' }}
              onMouseEnter={(e) => { if (activeThreadId !== thread.id) e.currentTarget.style.background = 'var(--ice-bg-hover)' }}
              onMouseLeave={(e) => { if (activeThreadId !== thread.id) e.currentTarget.style.background = 'transparent' }}>
              <Space direction="vertical" size={2} style={{ flex: 1, overflow: 'hidden' }}>
                <Text style={{ color: activeThreadId === thread.id ? primaryColor : 'var(--ice-text-primary)', fontWeight: activeThreadId === thread.id ? 600 : 400, fontSize: 13 }} ellipsis>{thread.title}</Text>
                <Text type="secondary" style={{ fontSize: 11 }}>{new Date(thread.updated_at).toLocaleDateString('zh-CN')}</Text>
              </Space>
              <Dropdown menu={{ items: threadMenuItems(thread) }} placement="bottomRight">
                <MoreOutlined style={{ color: 'var(--ice-text-muted)', cursor: 'pointer', marginLeft: 8 }} onClick={(e) => e.stopPropagation()} />
              </Dropdown>
            </div>
          ))}
        </div>

        {/* 底部：刷新 */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--ice-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>{threads.length} 个会话</Text>
          <Button type="text" size="small" icon={<ReloadOutlined />} onClick={refreshMessages} disabled={!activeThreadId} style={{ color: 'var(--ice-text-muted)' }} />
        </div>
      </div>

      {/* 右侧聊天区域 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* 聊天头部 */}
        <div style={{ padding: '12px 24px', borderBottom: '1px solid var(--ice-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--ice-bg-card)' }}>
          <Space>
            <Text strong style={{ color: 'var(--ice-text-primary)' }}>{activeAgent?.name || '选择 Agent'}</Text>
            {activeAgent && <Tag color="cyan" style={{ marginLeft: 8 }}>{activeAgent.model_name}</Tag>}
          </Space>
          {activeThreadId && <Button type="text" size="small" icon={<ReloadOutlined />} onClick={refreshMessages} style={{ color: 'var(--ice-text-muted)' }} title="刷新消息" />}
        </div>

        {/* 消息区域 */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px', background: 'var(--ice-bg-primary)' }}>
          {!activeThreadId ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--ice-text-muted)' }}>
              <div style={{ width: 80, height: 80, borderRadius: '50%', background: `${primaryColor}22`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
                <RobotOutlined style={{ fontSize: 40, color: primaryColor, opacity: 0.6 }} />
              </div>
              <Title level={4} style={{ color: 'var(--ice-text-secondary)', margin: '0 0 8px 0' }}>开始对话</Title>
              <Text type="secondary">选择或创建一个会话开始与 {activeAgent?.name || 'Agent'} 对话</Text>
            </div>
          ) : messages.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--ice-text-muted)' }}>
              <div style={{ width: 80, height: 80, borderRadius: '50%', background: `${primaryColor}22`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
                <RobotOutlined style={{ fontSize: 40, color: primaryColor, opacity: 0.6 }} />
              </div>
              <Title level={4} style={{ color: 'var(--ice-text-secondary)', margin: '0 0 8px 0' }}>空空如也</Title>
              <Text type="secondary">发送第一条消息开始对话</Text>
            </div>
          ) : (
            <div style={{ maxWidth: 800, margin: '0 auto' }}>
              {messages.map((msg, idx) => (
                <div key={msg.id || idx} style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'flex-start', ...(msg.role === 'user' ? { flexDirection: 'row-reverse' } : {}) }}>
                  <div style={{ width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    background: msg.role === 'user' ? primaryColor : `${accentColor}33`,
                    color: msg.role === 'user' ? '#fff' : primaryColor, fontSize: 16 }}>
                    {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                  </div>
                  <div style={{ flex: 1, maxWidth: '75%', background: msg.role === 'user' ? `${primaryColor}15` : 'var(--ice-bg-card)',
                    borderRadius: 12, padding: '12px 16px',
                    border: `1px solid ${msg.role === 'user' ? primaryColor + '33' : 'var(--ice-border)'}` }}>
                    {msg.role === 'assistant' ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown> : <Text style={{ color: 'var(--ice-text-primary)', lineHeight: 1.6 }}>{msg.content}</Text>}
                    <div style={{ marginTop: 6, fontSize: 11, color: 'var(--ice-text-muted)', textAlign: msg.role === 'user' ? 'right' : 'left' }}>
                      {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* 输入区域 */}
        <div style={{ padding: '16px 24px', borderTop: '1px solid var(--ice-border)', background: 'var(--ice-bg-card)' }}>
          <div style={{ maxWidth: 800, margin: '0 auto' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', background: 'var(--ice-bg-primary)', borderRadius: 16, padding: '12px 16px',
              border: '1px solid var(--ice-border)', boxShadow: '0 2px 8px var(--ice-shadow-sm)' }}>
              <TextArea ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
                placeholder={activeThreadId ? '输入消息... (Enter 发送, Shift+Enter 换行)' : '请先选择或创建会话...'}
                disabled={sending || !activeThreadId} autoSize={{ minRows: 1, maxRows: 6 }}
                style={{ flex: 1, background: 'transparent', border: 'none', color: 'var(--ice-text-primary)', resize: 'none' }} />
              <Button type="primary" icon={<SendOutlined />} loading={sending} onClick={handleSend}
                disabled={!input.trim() || sending || !activeThreadId}
                style={{ background: primaryColor, borderColor: primaryColor, borderRadius: 12, width: 40, height: 40 }} />
            </div>
            <div style={{ textAlign: 'center', marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>AI 生成内容仅供参考 · {activeAgent?.name || '未选择 Agent'}</Text>
            </div>
          </div>
        </div>
      </div>

      {/* 新建会话弹窗 */}
      <Modal title="新建会话" open={showNewThreadModal} onCancel={() => { setShowNewThreadModal(false); setNewThreadTitle('') }} onOk={createThread} okText="创建" cancelText="取消">
        <Form layout="vertical">
          <Form.Item label="会话标题" required>
            <Input placeholder="输入会话标题..." value={newThreadTitle} onChange={(e) => setNewThreadTitle(e.target.value)} onPressEnter={createThread} autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}


