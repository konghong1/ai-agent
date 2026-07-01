import { useCallback, useEffect, useState, useRef } from "react"
import { Typography, Input, Button, message, Modal, Avatar, Space } from "antd"
import {
  SendOutlined, PlusOutlined, DeleteOutlined, ReloadOutlined, EditOutlined,
  RobotOutlined, UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
} from "@ant-design/icons"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useLayoutStore } from "@/stores/layout"
import { authHeaders } from "@/services/auth"
import { useAuthStore } from "@/stores/auth"
import ChatSelector from "@/components/ChatSelector"
import { useChatSelectors } from "@/stores/useChatSelectors"
import { useNavigate } from "react-router-dom"

const { Text, Title } = Typography
const { TextArea } = Input

interface PromptTemplate {
  id: number; name: string; system_prompt: string; variables: string[]; category: string; description: string; enabled: boolean; created_at: string
}

interface Thread {
  id: string
  title: string
  agent_id: number | null
  created_at: string
  updated_at: string
}

interface Message {
  id: number
  role: string
  content: string
  created_at: string
}

const themeColors: Record<string, { primary: string; accent: string }> = {
  techBlue: { primary: "#2563EB", accent: "#60A5FA" },
  naturalGreen: { primary: "#22C55E", accent: "#86EFAC" },
  elegantPurple: { primary: "#7C3AED", accent: "#A78BFA" },
}

export default function ChatInterface() {
  const theme = useLayoutStore((s) => s.theme)
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState("")
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const activeThreadIdRef = useRef<string | null>(null)  // ref to avoid closure issues
  
  const { providerId, modelName, templateId, setProviderAndModel, setTemplateId } = useChatSelectors()
  
  const colors = themeColors[theme] || themeColors.naturalGreen
  const primaryColor = colors.primary
  const accentColor = colors.accent
  
  // Sync ref with state
  useEffect(() => {
    activeThreadIdRef.current = activeThreadId
  }, [activeThreadId])
  
  const fetchThreads = useCallback(async () => {
    try {
      const res = await fetch(`/api/threads`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setThreads(data)
        // Use ref instead of state to avoid re-creating fetchThreads
        if (data.length > 0 && !activeThreadIdRef.current) {
          setActiveThreadId(data[0].id)
        }
      }
    } catch { /* ignore */ }
  }, [])

  const fetchMessages = useCallback(async (threadId: string) => {
    try {
      const res = await fetch(`/api/threads/${threadId}/messages`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setMessages(data)
      } else {
        setMessages([])
      }
    } catch {
      setMessages([])
    }
  }, [])  // No deps - fetches always use fresh URL

  useEffect(() => {
    fetch("/api/prompt-templates", { headers: authHeaders() })
      .then(async r => {
        if (!r.ok) return []
        const data = await r.json()
        return Array.isArray(data) ? data : []
      })
      .then(setTemplates)
      .catch(() => [])
  }, [])

  useEffect(() => { fetchThreads().finally(() => setLoading(false)) }, [])  // Run once on mount

  useEffect(() => {
    if (activeThreadId) {
      fetchMessages(activeThreadId)
    }
  }, [activeThreadId, fetchMessages])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Responsive sidebar
  useEffect(() => {
    const handleResize = () => {
      setSidebarCollapsed(window.innerWidth < 768)
    }
    handleResize()
    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
  }, [])

  // Removed: activeAgent no longer used (Agent selector removed from chat)

  const deleteThread = async (threadId: string) => {
    try {
      const res = await fetch(`/api/threads/${threadId}`, {
        method: "DELETE",
        headers: authHeaders(),
      })
      if (res.ok || res.status === 204) {
        setThreads(prev => prev.filter(t => t.id !== threadId))
        if (activeThreadId === threadId) {
          setActiveThreadId(null)
          setMessages([])
        }
        message.success("会话已删除")
      }
    } catch (e: any) {
      message.error(e.message || "删除失败")
    }
  }

  const refreshMessages = async () => {
    if (!activeThreadId) return
    await fetchMessages(activeThreadId)
    message.success("已刷新")
  }

  const renameThread = async (threadId: string, newTitle: string) => {
    try {
      const res = await fetch(`/api/threads/${threadId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ title: newTitle }),
      })
      if (res.ok) {
        setThreads(prev => prev.map(t => t.id === threadId ? { ...t, title: newTitle } : t))
        message.success("重命名成功")
      }
    } catch { /* silent */ }
  }

  const startRename = (thread: Thread) => {
    setRenamingThreadId(thread.id)
    setRenameValue(thread.title)
    setRenameModal(true)
  }

  const [renamingThreadId, setRenamingThreadId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [renameModal, setRenameModal] = useState(false)

  const handleRenameSubmit = () => {
    if (renamingThreadId && renameValue.trim()) {
      renameThread(renamingThreadId, renameValue.trim())
    }
    setRenameModal(false)
    setRenamingThreadId(null)
    setRenameValue("")
  }

  const handleSend = async () => {
    if (!inputValue.trim() || sending) return
    const messageContent = inputValue.trim()
    setInputValue("")
    setSending(true)

    // Auto-create thread if no active session
    let threadId = activeThreadId
    if (!threadId) {
      try {
      const res = await fetch(`/api/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ title: messageContent.slice(0, 20) || "新会话" }),
      })
        if (res.ok) {
          const data = await res.json()
          setThreads(prev => [data, ...prev])
          threadId = data.id
          setActiveThreadId(data.id)
        } else {
          setSending(false)
          return
        }
      } catch (e: any) {
        setMessages(prev => [
          ...prev,
          { id: Date.now(), role: "assistant", content: `创建会话失败：${e.message}`, created_at: new Date().toISOString() },
        ])
        setSending(false)
        return
      }
    }

    if (!threadId) { setSending(false); return }

    const userMsg: Message = {
      id: Date.now(),
      role: "user",
      content: messageContent,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          message: messageContent,
          thread_id: threadId,
          template_id: templateId,
          provider_id: providerId,
          model_name: modelName,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        const assistantMsg: Message = {
          id: Date.now() + 1,
          role: "assistant",
          content: data.answer,
          created_at: new Date().toISOString(),
        }
        setMessages(prev => [...prev, assistantMsg])
      } else {
        const _err = await res.json().catch(() => ({}))
        setMessages(prev => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant",
            content: `抱歉，暂时无法回复：${res.statusText || "服务不可用"}`,
            created_at: new Date().toISOString(),
          },
        ])
      }
    } catch (e: any) {
      setMessages(prev => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: `网络错误：${e.message}`,
          created_at: new Date().toISOString(),
        },
      ])
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const selectThread = (threadId: string) => {
    setActiveThreadId(threadId)
    if (window.innerWidth < 768) setSidebarCollapsed(true)
  }

  const handleNewThread = async () => {
    try {
      const res = await fetch(`/api/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ title: "新会话" }),
      })
      if (res.ok) {
        const data = await res.json()
        setThreads(prev => [data, ...prev])
        setActiveThreadId(data.id)
      }
    } catch { /* silent */ }
  }

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - d.getTime()
    if (diff < 60000) return "刚刚"
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
  }

  if (loading) {
    return (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: "100vh", background: "var(--ice-bg-primary)",
      }}>
        <Text type="secondary">加载中...</Text>
      </div>
    )
  }

  return (
    <div style={{
      display: "flex",
      height: "calc(100vh - 120px)",
      minHeight: 400,
      background: "var(--ice-bg-primary)",
      overflow: "hidden",
    }}>
      {/* ====== Sidebar ====== */}
      <div style={{
        width: sidebarCollapsed ? 0 : 240,
        minWidth: sidebarCollapsed ? 0 : 240,
        borderRight: "1px solid var(--ice-border)",
        background: "var(--ice-bg-secondary)",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.2s ease, min-width 0.2s ease",
        overflow: "hidden",
      }}>
  {/* Agent selector at top of sidebar */}
  <div style={{
    padding: "12px 16px",
    borderBottom: "1px solid var(--ice-border)",
  }}>
    <Button
      type="primary"
      icon={<PlusOutlined />}
      block
      onClick={handleNewThread}
      disabled={false}
      style={{
        background: primaryColor,
        borderColor: primaryColor,
        borderRadius: 8,
        height: 32,
        fontSize: 12,
      }}
    >
      新建会话
    </Button>
  </div>

        {/* Thread list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
          {threads.length === 0 ? (
            <div style={{
              textAlign: "center", padding: "32px 16px",
              color: "var(--ice-text-muted)", fontSize: 13,
            }}>
              <Text>暂无会话</Text>
            </div>
          ) : (
            threads.map(t => (
              <div
                key={t.id}
                onClick={() => selectThread(t.id)}
                style={{
                  padding: "10px 12px",
                  borderRadius: 8,
                  marginBottom: 4,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  background: activeThreadId === t.id ? `${primaryColor}15` : "transparent",
                  border: activeThreadId === t.id
                    ? `1px solid ${primaryColor}33`
                    : "1px solid transparent",
                  transition: "all 0.15s ease",
                }}
                onMouseEnter={e => {
                  if (activeThreadId !== t.id) {
                    (e.currentTarget as HTMLDivElement).style.background = "var(--ice-bg-hover)"
                  }
                }}
                onMouseLeave={e => {
                  if (activeThreadId !== t.id) {
                    (e.currentTarget as HTMLDivElement).style.background = "transparent"
                  }
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13,
                    color: activeThreadId === t.id ? primaryColor : "var(--ice-text-primary)",
                    fontWeight: activeThreadId === t.id ? 500 : 400,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}>
                    {t.title}
                  </div>
                  <div style={{
                    fontSize: 11,
                    color: "var(--ice-text-muted)",
                    marginTop: 2,
                  }}>
                    {formatDate(t.updated_at)}
                  </div>
                </div>
                <Space size={2}>
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={e => {
                      e.stopPropagation()
                      startRename(t)
                    }}
                    style={{ opacity: 0.5, flexShrink: 0 }}
                    onMouseEnter={e => ((e.currentTarget as HTMLButtonElement).style.opacity = "1")}
                    onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.opacity = "0.5")}
                  />
                  <Button
                    type="text"
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={e => {
                      e.stopPropagation()
                      deleteThread(t.id)
                    }}
                    style={{ opacity: 0.5, flexShrink: 0 }}
                    onMouseEnter={e => ((e.currentTarget as HTMLButtonElement).style.opacity = "1")}
                    onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.opacity = "0.5")}
                  />
                </Space>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ====== Main Chat Area ====== */}
      <div style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        overflow: "hidden",
      }}>
        {/* Chat header */}
        <div style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--ice-border)",
          background: "var(--ice-bg-card)",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}>
          <Button
            type="text"
            icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            style={{
              color: "var(--ice-text-primary)",
              fontSize: 16,
              padding: "4px",
            }}
            title={sidebarCollapsed ? "展开侧栏" : "收起侧栏"}
          />
          <Text strong style={{ fontSize: 15, color: "var(--ice-text-primary)" }}>
            {threads.find(t => t.id === activeThreadId)?.title || '聊天'}
          </Text>
          {activeThreadId && (
            <>
              <div style={{ flex: 1 }} />
              <Button
                type="text"
                size="small"
                icon={<ReloadOutlined />}
                onClick={refreshMessages}
                style={{ color: "var(--ice-text-secondary)" }}
                title="刷新消息"
              />
            </>
          )}
        </div>

        {/* Messages area */}
        <div style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px 24px",
          background: "var(--ice-bg-primary)",
        }}>
          {!activeThreadId ? (
            <div style={{
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              height: "100%", color: "var(--ice-text-muted)",
            }}>
              <div style={{
                width: 56, height: 56, borderRadius: "50%",
                background: `${primaryColor}18`,
                display: "flex", alignItems: "center", justifyContent: "center",
                marginBottom: 16,
              }}>
                <RobotOutlined style={{ fontSize: 28, color: primaryColor, opacity: 0.6 }} />
              </div>
              <Title level={5} style={{ color: "var(--ice-text-secondary)", margin: "0 0 8px 0" }}>
                开始对话
              </Title>
              <Text type="secondary" style={{ fontSize: 13 }}>
                选择或创建一个会话开始对话
              </Text>
            </div>
          ) : messages.length === 0 ? (
            <div style={{
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              height: "100%", color: "var(--ice-text-muted)",
            }}>
              <div style={{
                width: 56, height: 56, borderRadius: "50%",
                background: `${primaryColor}18`,
                display: "flex", alignItems: "center", justifyContent: "center",
                marginBottom: 16,
              }}>
                <RobotOutlined style={{ fontSize: 28, color: primaryColor, opacity: 0.6 }} />
              </div>
              <Title level={5} style={{ color: "var(--ice-text-secondary)", margin: "0 0 8px 0" }}>
                空空如也
              </Title>
              <Text type="secondary" style={{ fontSize: 13 }}>
                发送第一条消息开始对话
              </Text>
            </div>
          ) : (
            <div>
              {messages.map((msg, idx) => (
                <div
                  key={msg.id || idx}
                  style={{
                    display: "flex",
                    gap: 10,
                    marginBottom: 16,
                    alignItems: "flex-start",
                    flexDirection: msg.role === "user" ? "row-reverse" : "row",
                  }}
                >
                  {/* Avatar */}
                  <Avatar
                    size="small"
                    icon={msg.role === "user" ? <UserOutlined /> : <RobotOutlined />}
                    style={{
                      background: msg.role === "user" ? primaryColor : `${accentColor}33`,
                      color: msg.role === "user" ? "#fff" : primaryColor,
                      marginTop: 2,
                      flexShrink: 0,
                    }}
                  />
                  {/* Bubble */}
                  <div style={{
                    maxWidth: "80%",
                    minWidth: 60,
                  }}>
                    <div style={{
                      background: msg.role === "user"
                        ? `${primaryColor}12`
                        : "var(--ice-bg-card)",
                      borderRadius: 12,
                      padding: "10px 14px",
                      border: msg.role === "user"
                        ? `1px solid ${primaryColor}22`
                        : `1px solid var(--ice-border)`,
                    }}>
                      {msg.role === "assistant" ? (
                        <div style={{
                          color: "var(--ice-text-primary)",
                          fontSize: 14,
                          lineHeight: 1.7,
                        }}>
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              code: ({ className, children, inline, ...props }) => {
                                const isInline = inline
                                if (isInline) {
                                  return (
                                    <code
                                      style={{
                                        background: "rgba(139,142,155,0.12)",
                                        padding: "2px 6px",
                                        borderRadius: 4,
                                        fontSize: "0.88em",
                                        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                                        color: "var(--ice-text-primary)",
                                      }}
                                      {...props}
                                    >
                                      {children}
                                    </code>
                                  )
                                }
                                return (
                                  <pre style={{
                                    background: "var(--ice-bg-secondary)",
                                    border: "1px solid var(--ice-border)",
                                    borderRadius: 8,
                                    padding: "12px 16px",
                                    overflow: "auto",
                                    margin: "8px 0",
                                    fontSize: 13,
                                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                                    lineHeight: 1.5,
                                  }}>
                                    <code className={className} {...props}>
                                      {children}
                                    </code>
                                  </pre>
                                )
                              },
                              table: ({ children, ...props }) => (
                                <div style={{ overflowX: "auto", margin: "8px 0" }}>
                                  <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }} {...props}>
                                    {children}
                                  </table>
                                </div>
                              ),
                              th: ({ children, ...props }) => (
                                <th style={{ padding: "8px 12px", border: `1px solid var(--ice-border)`, background: "var(--ice-bg-secondary)", fontWeight: 600, textAlign: "left" }} {...props}>
                                  {children}
                                </th>
                              ),
                              td: ({ children, ...props }) => (
                                <td style={{ padding: "8px 12px", border: `1px solid var(--ice-border)`, textAlign: "left" }} {...props}>
                                  {children}
                                </td>
                              ),
                              blockquote: ({ children, ...props }) => (
                                <blockquote style={{ borderLeft: `3px solid ${primaryColor}44`, paddingLeft: 12, margin: "8px 0", color: "var(--ice-text-secondary)", fontStyle: "italic" }} {...props}>
                                  {children}
                                </blockquote>
                              ),
                              ul: ({ children, ...props }) => (
                                <ul style={{ paddingLeft: 20, margin: "6px 0", lineHeight: 1.8 }} {...props}>
                                  {children}
                                </ul>
                              ),
                              ol: ({ children, ...props }) => (
                                <ol style={{ paddingLeft: 20, margin: "6px 0", lineHeight: 1.8 }} {...props}>
                                  {children}
                                </ol>
                              ),
                              p: ({ children, ...props }) => (
                                <p style={{ margin: "4px 0" }} {...props}>
                                  {children}
                                </p>
                              ),
                            }}
                          >
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <Text style={{
                          color: "var(--ice-text-primary)",
                          fontSize: 14,
                          lineHeight: 1.7,
                          whiteSpace: "pre-wrap",
                        }}>
                          {msg.content}
                        </Text>
                      )}
                      {/* Timestamp */}
                      <div style={{
                        marginTop: 6,
                        fontSize: 11,
                        color: "var(--ice-text-muted)",
                        textAlign: msg.role === "user" ? "right" : "left",
                      }}>
                        {new Date(msg.created_at).toLocaleString("zh-CN", {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {sending && (
                <div style={{
                  display: "flex", gap: 10, marginBottom: 16, alignItems: "flex-start",
                }}>
                  <Avatar size="small" icon={<RobotOutlined />} style={{
                    background: `${accentColor}33`,
                    color: primaryColor,
                    marginTop: 2,
                  }} />
                  <div style={{
                    background: "var(--ice-bg-card)",
                    borderRadius: 12,
                    padding: "10px 16px",
                    border: `1px solid var(--ice-border)`,
                    display: "flex",
                    gap: 4,
                    alignItems: "center",
                  }}>
                    <div style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: "var(--ice-text-muted)",
                      animation: "pulse 1.4s infinite ease-in-out",
                    }} />
                    <div style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: "var(--ice-text-muted)",
                      animation: "pulse 1.4s infinite ease-in-out 0.2s",
                    }} />
                    <div style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: "var(--ice-text-muted)",
                      animation: "pulse 1.4s infinite ease-in-out 0.4s",
                    }} />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div style={{
          padding: "12px 24px 16px",
          borderTop: "1px solid var(--ice-border)",
          background: "var(--ice-bg-card)",
        }}>
          <div style={{
            display: "flex",
            gap: 10,
            alignItems: "flex-end",
            background: "var(--ice-bg-primary)",
            borderRadius: 14,
            padding: "10px 14px",
            border: "1px solid var(--ice-border)",
            boxShadow: "0 2px 8px var(--ice-shadow-sm)",
          }}>
            <TextArea
              ref={inputRef}
              value={inputValue}
              onKeyDown={handleKeyDown}
              onChange={e => setInputValue(e.target.value)}
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              autoSize={{ minRows: 1, maxRows: 5 }}
              style={{
                flex: 1,
                background: "transparent",
                border: "none",
                color: "var(--ice-text-primary)",
                resize: "none",
                fontSize: 14,
              }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              loading={sending}
              onClick={handleSend}
              disabled={!inputValue.trim() || sending}
              style={{
                background: primaryColor,
                borderColor: primaryColor,
                borderRadius: 10,
                width: 38,
                height: 38,
                flexShrink: 0,
              }}
            />
          </div>
          
          {/* ChatSelector below input */}
          <ChatSelector
            providerId={providerId}
            modelName={modelName}
            templateId={templateId}
            templates={templates}
            onProviderChange={(pid, mname) => setProviderAndModel(pid, mname)}
            onTemplateChange={(tid) => setTemplateId(tid)}
            onNewThread={handleNewThread}
          />
          
          <div style={{ textAlign: "center", marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              AI 生成内容仅供参考
            </Text>
          </div>
        </div>
      </div>

      {/* Rename modal */}
      <Modal
        title="重命名会话"
        open={renameModal}
        onCancel={() => { setRenameModal(false); setRenamingThreadId(null) }}
        onOk={handleRenameSubmit}
        okText="重命名"
        cancelText="取消"
        okButtonProps={{ style: { background: primaryColor, borderColor: primaryColor } }}
      >
        <Typography.Text>会话标题</Typography.Text>
        <Input
          placeholder="输入会话标题..."
          value={renameValue}
          onChange={e => setRenameValue(e.target.value)}
          onPressEnter={handleRenameSubmit}
          autoFocus
          style={{ marginTop: 8 }}
        />
      </Modal>

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  )
}



