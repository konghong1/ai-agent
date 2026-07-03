import { useCallback, useEffect, useState, useRef } from "react"
import { Typography, Input, Button, message, Modal, Avatar, Space, Dropdown } from "antd"
import {
  SendOutlined, PlusOutlined, DeleteOutlined, ReloadOutlined, EditOutlined,
  RobotOutlined, UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
} from "@ant-design/icons"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useLayoutStore } from "@/stores/layout"
import { authHeaders, getToken } from "@/services/auth"
import ChatSelector from "@/components/ChatSelector"
import { useChatSelectors } from "@/stores/useChatSelectors"
import MediaCard, { MediaCardStyles } from "@/components/MediaCard"
import MediaLightbox, { type LightboxImage } from "@/components/MediaLightbox"

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
  blocks?: {
    type: string
    image_url?: string
    images?: { url: string }[]
    task_id?: string
    video_id?: string
    status?: string
    provider_id?: number
    error?: string
    video_url?: string
  } | null
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
  
  const { providerId, providerType, modelName, templateId, setProviderAndModel, setTemplateId } = useChatSelectors()
  
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
        // 后端返回 extra.blocks，拍平到顶层 msg.blocks
        const mapped = (data as any[]).map((msg: any) => ({
          ...msg,
          blocks: msg.extra?.blocks ?? msg.blocks ?? null,
        }))
        setMessages(mapped)
      } else {
        setMessages([])
      }
    } catch {
      setMessages([])
    }
  }, [])  // No deps - fetches always use fresh URL

  // ── Lightbox state ──────────────────────────────────────────────
  const [lightboxState, setLightboxState] = useState<{
    images: LightboxImage[]
    index: number
  } | null>(null)

  // ── Video status — SSE real-time push with auto-reconnect ──────────
  const esRef = useRef<Map<number, EventSource>>(new Map())  // msgId → EventSource
  const retryRef = useRef<Map<number, number>>(new Map())    // msgId → retry count
  const reconnectTimerRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const MAX_RETRIES = 5
  const BASE_RETRY_DELAY = 2000 // 2s, 4s, 8s, 16s, 32s

  const watchVideo = useCallback((msg: Message) => {
    const { task_id, provider_id, video_id } = msg.blocks!;
    if (!task_id || !provider_id) return;

    // Close any existing connection for this message
    const existingEs = esRef.current.get(msg.id);
    if (existingEs) {
      existingEs.close();
      esRef.current.delete(msg.id);
    }

    const token = getToken();
    const params = new URLSearchParams({ provider_id: String(provider_id) });
    if (video_id) params.append("video_id", video_id as string);
    if (token) params.append("token", token);

    const url = `/api/videos/${task_id}/watch?${params}`;
    const es = new EventSource(url);

    es.onopen = () => {
      // Connection established — reset retry count
      retryRef.current.set(msg.id, 0);
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status === "completed") {
          setMessages(prev =>
            prev.map(m =>
              m.id === msg.id
                ? { ...m, blocks: { ...m.blocks!, status: "completed", video_url: data.video_url || "" }, content: "视频已生成" }
                : m
            )
          );
          es.close();
          esRef.current.delete(msg.id);
          retryRef.current.delete(msg.id);
          const timer = reconnectTimerRef.current.get(msg.id);
          if (timer) { clearTimeout(timer); reconnectTimerRef.current.delete(msg.id); }
        } else if (data.status === "failed") {
          setMessages(prev =>
            prev.map(m =>
              m.id === msg.id
                ? { ...m, blocks: { ...m.blocks!, status: "failed", error: data.error || "" }, content: "视频生成失败" }
                : m
            )
          );
          es.close();
          esRef.current.delete(msg.id);
          retryRef.current.delete(msg.id);
          const timer = reconnectTimerRef.current.get(msg.id);
          if (timer) { clearTimeout(timer); reconnectTimerRef.current.delete(msg.id); }
        } else if (data.status === "processing" || data.status === "queued") {
          // Update progress info so the user sees the video is still being worked on
          setMessages(prev =>
            prev.map(m =>
              m.id === msg.id
                ? { ...m, blocks: { ...m.blocks!, status: "processing", progress: data.poll_count || 0 } }
                : m
            )
          );
        }
      } catch { /* ignore malformed events */ }
    };

    es.onerror = () => {
      es.close();
      esRef.current.delete(msg.id);

      // Exponential backoff reconnection
      const currentRetry = retryRef.current.get(msg.id) || 0;
      if (currentRetry < MAX_RETRIES) {
        const delay = BASE_RETRY_DELAY * Math.pow(2, currentRetry);
        retryRef.current.set(msg.id, currentRetry + 1);
        const timer = setTimeout(() => {
          reconnectTimerRef.current.delete(msg.id);
          // Check if the message is still in processing state before reconnecting
          setMessages(prev => {
            const current = prev.find(m => m.id === msg.id);
            if (current?.blocks?.status === "processing") {
              watchVideo(msg);
            } else {
              retryRef.current.delete(msg.id);
            }
            return prev;
          });
        }, delay);
        reconnectTimerRef.current.set(msg.id, timer);
      } else {
        // Max retries exceeded — mark as failed
        retryRef.current.delete(msg.id);
        setMessages(prev =>
          prev.map(m =>
            m.id === msg.id
              ? { ...m, blocks: { ...m.blocks!, status: "failed", error: "连接超时，请刷新页面重试" }, content: "视频状态监控超时" }
              : m
          )
        );
      }
    };

    esRef.current.set(msg.id, es);
  }, []);

  // Cleanup EventSources on unmount
  useEffect(() => {
    return () => {
      esRef.current.forEach(es => es.close());
      esRef.current.clear();
      reconnectTimerRef.current.forEach(t => clearTimeout(t));
      reconnectTimerRef.current.clear();
      retryRef.current.clear();
    };
  }, []);

  // Auto-connect SSE for new "processing" video messages
  useEffect(() => {
    messages.forEach(msg => {
      if (
        msg.blocks?.type === "video" &&
        msg.blocks?.status === "processing" &&
        msg.blocks?.task_id &&
        !esRef.current.has(msg.id) &&
        !reconnectTimerRef.current.has(msg.id)
      ) {
        watchVideo(msg);
      }
    });
  }, [messages, watchVideo]);

  // Cleanup completed/failed ES connections when state updates
  useEffect(() => {
    messages.forEach(msg => {
      if (
        msg.blocks?.type === "video" &&
        (msg.blocks?.status === "completed" || msg.blocks?.status === "failed") &&
        esRef.current.has(msg.id)
      ) {
        esRef.current.get(msg.id)?.close();
        esRef.current.delete(msg.id);
        retryRef.current.delete(msg.id);
        const timer = reconnectTimerRef.current.get(msg.id);
        if (timer) { clearTimeout(timer); reconnectTimerRef.current.delete(msg.id); }
      }
    });
  }, [messages]);
  // ── End video SSE watching ────────────────────────────────────────

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
    if (!providerId || !modelName) {
      Modal.warning({
        title: '请先选择模型',
        content: '请在上方选择一个 AI 模型后再发送消息',
        okText: '知道了',
      })
      return
    }
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
        body: JSON.stringify({ title: messageContent.slice(0, 8) || "新会话" }),
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

    // Use SSE streaming
    let fetchRes: Response | null = null
    try {
      fetchRes = await fetch("/api/chat-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          message: messageContent,
          thread_id: threadId,
          template_id: templateId,
          provider_id: providerId,
          provider_type: providerType || 'openai-compatible',
          model_name: modelName,
        }),
      })

      if (fetchRes.ok) {
        // SSE streaming handler
        const reader = fetchRes.body?.getReader()
        const decoder = new TextDecoder()
            let assistantContent = ""
            let finalThreadId = threadId
            let assistantBlocks: any = null

            if (reader) {
              while (true) {
                const { done, value } = await reader.read()
                if (done) break

                const chunk = decoder.decode(value, { stream: true })
                const lines = chunk.split('\n')

                for (const line of lines) {
                  if (line.startsWith('data: ')) {
                    try {
                      const data = JSON.parse(line.slice(6))
                      if (data.answer !== undefined) {
                        // Final response
                        assistantContent = data.answer
                        finalThreadId = data.thread_id
                        if (data.blocks) {
                          assistantBlocks = data.blocks
                        }
                      }
                    } catch {
                      // Ignore parse errors for partial SSE messages
                    }
                  }
                }
              }

              // Send assistant message
              if (assistantContent) {
                const assistantMsg: Message = {
                  id: Date.now() + 1,
                  role: "assistant",
                  content: assistantContent,
                  created_at: new Date().toISOString(),
                  blocks: assistantBlocks,
                }
            setMessages(prev => [...prev, assistantMsg])
            
            // Update thread list with new thread if created
            if (finalThreadId !== threadId) {
              setThreads(prev => {
                const exists = prev.find(t => t.id === finalThreadId)
                if (exists) return prev
                return [{ id: finalThreadId, title: messageContent.slice(0, 60), agent_id: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }, ...prev]
              })
              setActiveThreadId(finalThreadId)
            }
          }
        }
      } else {
        await fetchRes.json().catch(() => {})
        setMessages(prev => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant",
            content: `抱歉，暂时无法回复：${fetchRes?.statusText || "服务不可用"}`,
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

  // Fix: properly handle error for non-ok response in the catch block
  // (already handled above, this is just a placeholder for clarity)

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
              <Dropdown
                key={t.id}
                trigger={["contextMenu"]}
                menu={{
                  items: [
                    { key: "rename", label: "重命名", icon: <EditOutlined />, onClick: () => startRename(t) },
                    { key: "delete", label: "删除", icon: <DeleteOutlined />, danger: true, onClick: () => deleteThread(t.id) },
                  ],
                }}
              >
                <div
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
              </Dropdown>
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
                          {/* ── Media Card (Image or Video) ── */}
                          {(msg.blocks?.type === "image" || msg.blocks?.type === "video") && (
                            <div
                              style={{
                                cursor: msg.blocks.type === "image" ? "pointer" : "default",
                                position: "relative",
                              }}
                              onClick={() => {
                                if (msg.blocks?.type === "image" && msg.blocks.image_url) {
                                  const allImages: LightboxImage[] = [
                                    { url: msg.blocks.image_url, alt: "生成图片" },
                                    ...(msg.blocks.images?.map((img) => ({
                                      url: img.url,
                                      alt: "生成图片",
                                    })) || []),
                                  ]
                                  setLightboxState({ images: allImages, index: 0 })
                                }
                              }}
                            >
                              <MediaCard
                                block={
                                  msg.blocks.type === "image"
                                    ? {
                                        type: "image" as const,
                                        image_url: msg.blocks.image_url!,
                                        images: msg.blocks.images,
                                      }
                                    : {
                                        type: "video" as const,
                                        task_id: msg.blocks.task_id!,
                                        status: (msg.blocks.status || "processing") as any,
                                        video_url: msg.blocks.video_url,
                                        error: msg.blocks.error,
                                        provider_id: msg.blocks.provider_id,
                                      }
                                }
                                primaryColor={primaryColor}
                                accentColor={accentColor}
                                isUserMessage={false}
                                onContentLoaded={() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })}
                                onThumbnailClick={(index) => {
                                  if (msg.blocks?.type === "image" && msg.blocks.image_url) {
                                    const allImages: LightboxImage[] = [
                                      { url: msg.blocks.image_url, alt: "生成图片" },
                                      ...(msg.blocks.images?.map((img) => ({
                                        url: img.url,
                                        alt: "生成图片",
                                      })) || []),
                                    ]
                                    setLightboxState({ images: allImages, index })
                                  }
                                }}
                              />
                              {/* Multi-image thumb clicks handled by lightbox */}
                              {msg.blocks.type === "image" && msg.blocks.images && msg.blocks.images.length > 1 && (
                                <div style={{ position: "relative" }}>
                                  {/* Invisible click targets for thumbnails rendered by MediaCard */}
                                  {/* We intercept clicks via event delegation */}
                                </div>
                              )}
                            </div>
                          )}
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              code: ({ className, children, ...props }: any) => {
                                const isInline = !className || (typeof children === 'string' && !children.includes('\n'))
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
                                    {...props as any}
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
                              // 屏蔽 markdown 原生图片渲染（MediaCard 已处理）
                              img: () => null,
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

        {/* Input area — single unified input box */}
        <div style={{
          padding: "0 16px 12px",
          background: "#F8FAFC",
        }}>
          <div style={{
            display: "flex",
            flexDirection: "column",
            border: "1px solid #d0d0d0",
            borderRadius: 12,
            background: "#fff",
            padding: "12px 16px",
          }}>
            {/* Kill the TextArea border/focus ring so it looks seamless inside the outer box */}
            <style>{`
              .chat-input-textarea,
              .chat-input-textarea.ant-input,
              .chat-input-textarea:hover,
              .chat-input-textarea.ant-input:hover,
              .chat-input-textarea:focus,
              .chat-input-textarea.ant-input:focus,
              .chat-input-textarea-focused,
              .chat-input-textarea.ant-input-focused {
                border: none !important;
                box-shadow: none !important;
                outline: none !important;
                background: transparent !important;
              }
            `}</style>

            <TextArea
              ref={inputRef}
              value={inputValue}
              onKeyDown={handleKeyDown}
              onChange={e => setInputValue(e.target.value)}
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              autoSize={{ minRows: 1, maxRows: 5 }}
              className="chat-input-textarea"
              style={{
                width: "100%",
                background: "transparent",
                border: "none",
                color: "#333",
                resize: "none",
                fontSize: 14,
                padding: 0,
                marginBottom: 8,
              }}
            />

            {/* Toolbar: selectors (left) + send button (right) */}
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}>
              <ChatSelector
                providerId={providerId}
                providerType={providerType}
                modelName={modelName}
                templateId={templateId}
                templates={templates}
                onProviderChange={(pid, mname, ptype) => setProviderAndModel(pid, mname, ptype)}
                onTemplateChange={(tid) => setTemplateId(tid)}
              />
              <span style={{ flex: 1 }} />
              <Button
                type="primary"
                icon={<SendOutlined />}
                loading={sending}
                onClick={handleSend}
                disabled={!inputValue.trim() || sending || !providerId || !modelName}
                style={{
                  background: primaryColor,
                  borderColor: primaryColor,
                  borderRadius: "50%",
                  width: 38,
                  height: 38,
                  flexShrink: 0,
                }}
              />
            </div>
          </div>

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

      {/* MediaCard styles */}
      <MediaCardStyles />

      {/* Media Lightbox */}
      {lightboxState && (
        <MediaLightbox
          images={lightboxState.images}
          currentIndex={lightboxState.index}
          primaryColor={primaryColor}
          onClose={() => setLightboxState(null)}
          onNavigate={(idx) => setLightboxState(s => s ? { ...s, index: idx } : null)}
        />
      )}
    </div>
  )
}
