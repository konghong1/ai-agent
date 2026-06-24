import React, { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Row, Col, Card, Typography, Input, Button, Space, Tag, Collapse, Divider, message, Spin } from 'antd'
import { ArrowLeftOutlined, SendOutlined, UserOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { IceCrystalCard } from '@/components/IceCrystalCard'

const { Text, Title } = Typography
const { TextArea } = Input

interface Agent {
  id: number; name: string; description: string; system_prompt: string
  model_provider: string; model_name: string; temperature: number; enabled: boolean
}

interface Message {
  id: number; role: string; content: string; created_at: string
}

export default function AgentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    Promise.all([
      fetch(`/api/agents/${id}`, { headers: authHeaders() }).then(r => r.json()),
      fetch(`/api/agents/${id}/threads`, { headers: authHeaders() }).then(r => r.json()).catch(() => []),
    ]).then(([agentData, threadsData]) => {
      setAgent(agentData)
      if (threadsData.length > 0) {
        setThreadId(threadsData[0].id)
        fetchMessages(threadsData[0].id)
      }
      setLoading(false)
    })
  }, [id])

  const fetchMessages = async (tid: string) => {
    try {
      const res = await fetch(`/api/threads/${tid}/messages`, { headers: authHeaders() })
      const data = await res.json()
      setMessages(data)
    } catch {}
  }

  const handleSend = async () => {
    if (!input.trim() || sending || !id) return
    setSending(true)
    const userMsg: Message = { id: Date.now(), role: 'user', content: input, created_at: new Date().toISOString() }
    setMessages(prev => [...prev, userMsg])
    setInput('')

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ agent_id: Number(id), message: input, thread_id: threadId || undefined }),
      })
      const data = await res.json()
      const assistantMsg: Message = { id: Date.now() + 1, role: 'assistant', content: data.answer, created_at: new Date().toISOString() }
      setMessages(prev => [...prev, assistantMsg])
      setThreadId(data.thread_id)
    } catch (e: any) {
      message.error(e.message || '发送失败')
    } finally {
      setSending(false)
    }
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (loading) return <div style={{ textAlign: 'center', paddingTop: 80 }}><Spin size="large" /></div>

  return (
    <div>
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/agents')}
        style={{ color: '#e8f4f8', marginBottom: 16, padding: '4px 0' }}
      >
        返回 Agent 列表
      </Button>

      <Row gutter={24}>
        <Col span={8}>
          <IceCrystalCard hoverEffect="glow" animation="fadeInUp" title={agent?.name} style={{ background: 'rgba(17, 24, 39, 0.85)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>模型</Text>
                <div style={{ marginTop: 4 }}><Tag color="cyan">{agent?.model_name}</Tag></div>
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>温度</Text>
                <div style={{ marginTop: 4, color: '#00d4ff' }}>{agent?.temperature}</div>
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>描述</Text>
                <div style={{ marginTop: 4, color: '#e8f4f8' }}>{agent?.description || '-'}</div>
              </div>
              <Collapse items={[{ key: 'sp', label: '系统提示词', children: <Text style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{agent?.system_prompt}</Text> }]} />
            </div>
          </IceCrystalCard>
        </Col>

        <Col span={16}>
          <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ background: 'rgba(17, 24, 39, 0.85)', height: '100%', display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0', minHeight: 400 }}>
              {messages.length === 0 ? (
                <div style={{ textAlign: 'center', paddingTop: 120, color: '#556677' }}>
                  <BotOutlined style={{ fontSize: 48, opacity: 0.3 }} />
                  <p style={{ marginTop: 12 }}>开始与 Agent 对话</p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: msg.role === 'user' ? '#00d4ff' : '#7b68ee', color: '#fff', fontSize: 14, flexShrink: 0,
                    }}>
                      {msg.role === 'user' ? <span style={{fontSize:16}}>👤</span> : <span style={{fontSize:16}}>🤖</span>}
                    </div>
                    <div style={{ flex: 1, background: 'rgba(0, 212, 255, 0.04)', borderRadius: 12, padding: '12px 16px', border: '1px solid rgba(0, 212, 255, 0.08)' }}>
                      {msg.role === 'assistant' ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      ) : (
                        <Text style={{ color: '#e8f4f8' }}>{msg.content}</Text>
                      )}
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            <Divider style={{ margin: 0 }} />
            <div style={{ padding: 16, display: 'flex', gap: 8 }}>
              <TextArea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPressEnter={(e) => { if (!e.shiftKey) handleSend() }}
                autoSize={{ minRows: 1, maxRows: 4 }}
                placeholder="输入消息..."
                disabled={sending}
                style={{ flex: 1 }}
              />
              <Button type="primary" icon={<SendOutlined />} loading={sending} onClick={handleSend} style={{ alignSelf: 'flex-end' }}>
                发送
              </Button>
            </div>
          </IceCrystalCard>
        </Col>
      </Row>
    </div>
  )
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('agent-token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

