import { useCallback, useEffect, useLayoutEffect, useState, useRef } from "react"
import { Typography, Input, Button, message, Modal, Avatar, Space, Dropdown, Select, Tooltip, Popconfirm } from "antd"
import {
  SendOutlined, PlusOutlined, DeleteOutlined, ReloadOutlined, EditOutlined,
  RobotOutlined, UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  PictureOutlined, ControlOutlined, CopyOutlined,
} from "@ant-design/icons"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useLayoutStore } from "@/stores/layout"
import { authHeaders, getToken } from "@/services/auth"
import { proxyMediaUrl } from "@/services/media"
import ChatSelector from "@/components/ChatSelector"
import { useChatSelectors } from "@/stores/useChatSelectors"
import MediaCard, { MediaCardStyles } from "@/components/MediaCard"
import MediaLightbox, { type LightboxImage } from "@/components/MediaLightbox"

const { Text, Title } = Typography
const { TextArea } = Input

// Persist the currently-open chat thread so a browser refresh or navigating to
// another module and back doesn't lose the conversation.
const ACTIVE_THREAD_KEY = "active-chat-thread"

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
    reference_images?: string[]
  } | null
}

const themeColors: Record<string, { primary: string; accent: string }> = {
  techBlue: { primary: "#2563EB", accent: "#60A5FA" },
  naturalGreen: { primary: "#22C55E", accent: "#86EFAC" },
  elegantPurple: { primary: "#7C3AED", accent: "#A78BFA" },
}

// The video model requires num_frames to be of the form 8*n + 1
// (e.g. 1, 9, 17, 25, 33, ...). Given a desired duration (seconds) at the
// given fps, round to the nearest valid value so we never send an invalid
// frame count (which previously returned HTTP 400 from the provider).
export function toValidNumFrames(durationSec: number, fps = 24, max = 241): number {
  const ideal = Math.max(1, Math.round((durationSec || 0) * fps))
  let n = Math.round((ideal - 1) / 8)
  if (n < 0) n = 0
  let frames = 8 * n + 1
  // Keep the result within a safe upper bound that is itself 8*n + 1.
  if (frames > max) {
    const maxN = Math.floor((max - 1) / 8)
    frames = 8 * maxN + 1
  }
  return frames
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
  const chatAbortRef = useRef<AbortController | null>(null)  // abort SSE when switching threads
  const fetchMsgIdRef = useRef(0)  // race condition guard: only apply latest fetchMessages result
  const skipNextFetchRef = useRef(false)  // skip fetchMessages when creating a new thread (handleSend)

  // ── Message pagination (latest page + scroll-up history loading) ──
  const PAGE_SIZE = 20
  const [hasMoreHistory, setHasMoreHistory] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)          // messages scroll container
  const atBottomRef = useRef(true)                        // is the view currently at the bottom?
  const loadingHistoryRef = useRef(false)                 // guard against duplicate history fetches
  const hasMoreRef = useRef(false)                        // mirror of hasMoreHistory for handlers/closures
  const oldestIdRef = useRef<number | null>(null)        // cursor for the oldest loaded message
  const scrollPreserveRef = useRef<{ prevHeight: number; prevTop: number } | null>(null)  // restore position after prepend
  const scrollToBottomRef = useRef<"instant" | "smooth" | null>(null)  // controlled auto-scroll request

  // ── Reference images (图生图 / 图生视频) ──
  const [referenceImages, setReferenceImages] = useState<string[]>([])
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [genSize, setGenSize] = useState<string>("1024x1024")
  const [genDuration, setGenDuration] = useState<number>(5)
  const refInputRef = useRef<HTMLInputElement>(null)
  // Tracks whether the user manually picked an output size, so we don't
  // override their explicit choice when reference images change.
  const userPickedSizeRef = useRef(false)

  // Auto-match the generated image's aspect ratio to the first reference
  // image. Without this, a portrait/landscape photo uploaded as a reference
  // would still produce a square 1024x1024 output, which feels "比例失调"
  // compared to the original. The user's manual size choice always wins.
  useEffect(() => {
    if (referenceImages.length === 0) {
      userPickedSizeRef.current = false
      return
    }
    if (userPickedSizeRef.current) return
    const src = proxyMediaUrl(referenceImages[0])
    const img = new Image()
    img.onload = () => {
      const { naturalWidth: w, naturalHeight: h } = img
      if (!w || !h) return
      const ratio = w / h
      let size = "1024x1024"
      if (ratio < 0.85) size = "768x1024"      // portrait reference -> portrait output
      else if (ratio > 1.15) size = "1024x768"  // landscape reference -> landscape output
      setGenSize(size)
    }
    img.onerror = () => { /* keep current size if dimensions can't be read */ }
    img.src = src
  }, [referenceImages])
  
  const { providerId, providerType, modelName, modelType, templateId, setProviderAndModel, setTemplateId } = useChatSelectors()
  // 当前选中的提示词模板（用于聊天输入框上方的可见指示）
  const activeTemplate = templates.find((t) => t.id === templateId) || null

  // 选择提示词模板时，把模板的提示词内容带入输入框，方便用户查看/修改后再发送
  // （修复：之前仅显示已选模板标签，模板内容没有进入输入框）
  const handleTemplateChange = (tid: number) => {
    setTemplateId(tid)
    const tpl = templates.find((t) => t.id === tid)
    if (tpl) {
      setInputValue(tpl.system_prompt || '')
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }
  
  const colors = themeColors[theme] || themeColors.naturalGreen
  const primaryColor = colors.primary
  const accentColor = colors.accent
  
  // Wrapper for setActiveThreadId that also syncs the ref synchronously and
  // persists the selection so it survives a refresh / module switch.
  const switchThread = useCallback((threadId: string | null) => {
    activeThreadIdRef.current = threadId
    setActiveThreadId(threadId)
    try {
      if (threadId) localStorage.setItem(ACTIVE_THREAD_KEY, threadId)
      else localStorage.removeItem(ACTIVE_THREAD_KEY)
    } catch {
      /* storage may be unavailable (private mode) — non-fatal */
    }
  }, [])
  
  const fetchThreads = useCallback(async () => {
    try {
      const res = await fetch(`/api/threads`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setThreads(data)
        // Restore the previously-viewed thread (persisted in localStorage) so a
        // refresh or navigating away and back keeps the same conversation open.
        // Fall back to the first thread only if nothing was persisted or the
        // saved thread no longer exists.
        let target: string | null = null
        try {
          const saved = localStorage.getItem(ACTIVE_THREAD_KEY)
          if (saved && data.some((t: any) => t.id === saved)) target = saved
        } catch {
          /* storage unavailable — fall through to default */
        }
        if (!target && data.length > 0) target = data[0].id
        if (target) switchThread(target)
      } else {
        const err = await res.json().catch(() => ({}))
        message.error(err?.detail || `加载会话列表失败 (HTTP ${res.status})`, 4)
      }
    } catch {
      message.error('无法连接到后端服务，请确认后端已启动（端口 8010）', 5)
    }
  }, [switchThread])

  // 后端返回 extra.blocks，拍平到顶层 msg.blocks
  const mapMessages = (raw: any[]): Message[] =>
    (raw as any[]).map((msg: any) => ({
      ...msg,
      blocks: msg.extra?.blocks ?? msg.blocks ?? null,
    }))

  // Load only the latest page of messages for a thread (initial load / refresh).
  // This is the fix for "消息从头部重载": we no longer pull the whole history on
  // every open — just the most recent PAGE_SIZE, and the view stays at the bottom.
  const fetchLatest = useCallback(async (threadId: string) => {
    const reqId = ++fetchMsgIdRef.current

    try {
      const res = await fetch(`/api/threads/${threadId}/messages?limit=${PAGE_SIZE}`, {
        headers: authHeaders(),
      })
      // Guard: if a newer request was fired, discard this stale response
      if (reqId !== fetchMsgIdRef.current) return
      if (res.ok) {
        const data = await res.json()
        if (reqId !== fetchMsgIdRef.current) return  // double-check after await
        setMessages(mapMessages(data.messages || []))
        hasMoreRef.current = !!data.has_more
        setHasMoreHistory(!!data.has_more)
        oldestIdRef.current = (data.oldest_id as number) ?? null
        // After this render, jump to the newest message.
        scrollToBottomRef.current = "instant"
      } else {
        if (reqId !== fetchMsgIdRef.current) return
        setMessages([])
        hasMoreRef.current = false
        setHasMoreHistory(false)
        oldestIdRef.current = null
        const err = await res.json().catch(() => ({}))
        message.error(err?.detail || `加载消息失败 (HTTP ${res.status})`, 4)
      }
    } catch (e: any) {
      if (reqId !== fetchMsgIdRef.current) return
      setMessages([])
      hasMoreRef.current = false
      setHasMoreHistory(false)
      oldestIdRef.current = null
      message.error('无法连接到后端服务，请确认后端已启动（端口 8010）', 5)
    }
  }, [])  // No deps - fetches always use fresh URL

  // Load the previous (older) page when the user scrolls to the top, and
  // prepend it. The scroll position is preserved by fetchOlder + the
  // useLayoutEffect below, so the user's view never jumps.
  const fetchOlder = useCallback(async () => {
    const threadId = activeThreadIdRef.current
    if (!threadId || loadingHistoryRef.current || !hasMoreRef.current) return
    const before = oldestIdRef.current
    if (before == null) return

    loadingHistoryRef.current = true
    setLoadingHistory(true)
    // Capture scroll metrics BEFORE the DOM grows so we can restore the view.
    const el = scrollRef.current
    if (el) scrollPreserveRef.current = { prevHeight: el.scrollHeight, prevTop: el.scrollTop }
    try {
      const res = await fetch(
        `/api/threads/${threadId}/messages?limit=${PAGE_SIZE}&before=${before}`,
        { headers: authHeaders() },
      )
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        message.error(err?.detail || `加载历史消息失败 (HTTP ${res.status})`, 4)
        scrollPreserveRef.current = null
        return
      }
      const data = await res.json()
      // Prepend older messages; stable ids keep React from re-rendering existing rows.
      setMessages(prev => [...mapMessages(data.messages || []), ...prev])
      hasMoreRef.current = !!data.has_more
      setHasMoreHistory(!!data.has_more)
      oldestIdRef.current = (data.oldest_id as number) ?? null
    } catch {
      message.error('无法连接到后端服务，请确认后端已启动（端口 8010）', 5)
      scrollPreserveRef.current = null
    } finally {
      loadingHistoryRef.current = false
      setLoadingHistory(false)
    }
  }, [])

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
      if (chatAbortRef.current) chatAbortRef.current.abort();
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

  // 模板列表加载完成后，如果已选中某个模板，则把其提示词内容预填进输入框
  const prefillDoneRef = useRef(false)
  useEffect(() => {
    if (prefillDoneRef.current || templateId == null) return
    const tpl = templates.find((t) => t.id === templateId)
    if (tpl) {
      setInputValue(tpl.system_prompt || '')
      prefillDoneRef.current = true
    }
  }, [templateId, templates])

  useEffect(() => { fetchThreads().finally(() => setLoading(false)) }, [])  // Run once on mount

  useEffect(() => {
    if (activeThreadId) {
      // Skip fetch when handleSend just created a new thread — the user message
      // is already in state and the thread is empty on the backend
      if (skipNextFetchRef.current) {
        skipNextFetchRef.current = false
        return
      }
      fetchLatest(activeThreadId)
    } else {
      setMessages([])
      hasMoreRef.current = false
      setHasMoreHistory(false)
      oldestIdRef.current = null
    }
  }, [activeThreadId, fetchLatest])

  // Controlled scrolling. This replaces the old "scrollIntoView on every
  // messages change" which caused the screen to keep jumping to the head.
  //  - When prepending history we restore the exact scroll position so the
  //    user's view is stable.
  //  - Otherwise we only auto-scroll to bottom when explicitly requested
  //    (initial load, or a new message arriving while the user is at bottom).
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    if (scrollPreserveRef.current) {
      const { prevHeight, prevTop } = scrollPreserveRef.current
      const newHeight = el.scrollHeight
      el.scrollTop = prevTop + (newHeight - prevHeight)
      scrollPreserveRef.current = null
      return
    }
    if (scrollToBottomRef.current) {
      el.scrollTop = el.scrollHeight
      scrollToBottomRef.current = null
    }
  }, [messages])

  // Scroll handler: track bottom state and trigger history load near the top.
  const handleMessagesScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const distanceFromTop = el.scrollTop
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    atBottomRef.current = distanceFromBottom < 48
    // Load older messages when the user scrolls near the top (and more exist).
    if (distanceFromTop < 64 && hasMoreRef.current && !loadingHistoryRef.current) {
      fetchOlder()
    }
  }, [fetchOlder])

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
        // Update UI state FIRST so the row disappears immediately and every
        // subsequent delete always operates on a consistent, fresh list.
        // (Previously the active-thread cleanup ran before this filter, so any
        // throw in cleanup could abort the whole delete and leave the row stuck —
        // the classic "first delete works, second one won't" symptom.)
        setThreads(prev => prev.filter(t => t.id !== threadId))
        message.success("会话已删除")
        // Only the active thread needs SSE / timer cleanup. Use the ref (not the
        // closure `activeThreadId`) so the check is always current, and isolate
        // cleanup in its own try/catch so it can never block the delete.
        if (activeThreadIdRef.current === threadId) {
          try {
            chatAbortRef.current?.abort()
            chatAbortRef.current = null
            esRef.current.forEach(es => es.close())
            esRef.current.clear()
            reconnectTimerRef.current.forEach(t => clearTimeout(t))
            reconnectTimerRef.current.clear()
            retryRef.current.clear()
          } catch {
            /* cleanup is best-effort */
          }
          setMessages([])
          // Advance fetchMsgId so any in-flight fetchMessages discards its result
          fetchMsgIdRef.current++
          switchThread(null)
        }
      } else {
        const err = await res.json().catch(() => ({}))
        message.error(err?.detail || `删除失败 (HTTP ${res.status})`)
      }
    } catch (e: any) {
      message.error(e.message || "删除失败")
    }
  }

  const refreshMessages = async () => {
    if (!activeThreadId) return
    await fetchLatest(activeThreadId)
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
        body: JSON.stringify({ title: messageContent.slice(0, 5) || "新会话" }),
      })
        if (res.ok) {
          const data = await res.json()
          setThreads(prev => [data, ...prev])
          threadId = data.id
          // Skip the next fetchMessages — the thread is empty and we're about
          // to add the user's message to state ourselves
          skipNextFetchRef.current = true
          switchThread(data.id)
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
    // Only add user message if we're still on the same thread
    // (threadId could differ if user switched during thread creation)
    if (activeThreadIdRef.current === threadId || !activeThreadIdRef.current) {
      setMessages(prev => [...prev, userMsg])
      // The user just sent — pin the view to the bottom so they see their msg.
      scrollToBottomRef.current = "smooth"
    }

    // Use SSE streaming
    let fetchRes: Response | null = null
    const abortCtrl = new AbortController()
    chatAbortRef.current = abortCtrl
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
          reference_images: referenceImages,
          // 仅按模型类型下发对应参数：图片模型给 size，视频模型给 num_frames / frame_rate
          ...(modelType === 'image' ? { size: genSize } : {}),
          ...(modelType === 'video' ? { num_frames: toValidNumFrames(genDuration), frame_rate: 24 } : {}),
        }),
        signal: abortCtrl.signal,
      })
      setReferenceImages([])

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

              // Send assistant message — but only if user hasn't switched threads
              if (assistantContent && activeThreadIdRef.current === threadId) {
                const assistantMsg: Message = {
                  id: Date.now() + 1,
                  role: "assistant",
                  content: assistantContent,
                  created_at: new Date().toISOString(),
                  blocks: assistantBlocks,
                }
                // Only yank to bottom if the user is already there (don't rip
                // them out of history they're reading while the reply streams in).
                if (atBottomRef.current) scrollToBottomRef.current = "smooth"
                setMessages(prev => [...prev, assistantMsg])

                // Update thread list with new thread if created
                if (finalThreadId !== threadId) {
                  setThreads(prev => {
                    const exists = prev.find(t => t.id === finalThreadId)
                    if (exists) return prev
                    return [{ id: finalThreadId, title: messageContent.slice(0, 5) || "新会话", agent_id: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }, ...prev]
                  })
                  // Skip fetch — we already have the messages in state
                  skipNextFetchRef.current = true
                  switchThread(finalThreadId)
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
      // AbortError means the user switched threads — don't show an error
      if (e?.name === 'AbortError') return
      const errMsg = e?.message?.includes('Failed to fetch')
        ? '无法连接到后端服务，请确认后端已启动'
        : `网络错误：${e.message}`
      message.error(errMsg, 5)
      setMessages(prev => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: errMsg,
          created_at: new Date().toISOString(),
        },
      ])
    } finally {
      chatAbortRef.current = null
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
    // Use ref for accurate current value (state may be stale in closures)
    if (threadId === activeThreadIdRef.current) return

    // Abort any in-flight SSE chat stream from the previous thread
    if (chatAbortRef.current) {
      chatAbortRef.current.abort()
      chatAbortRef.current = null
    }

    // Close all video SSE connections from the previous thread
    esRef.current.forEach(es => es.close())
    esRef.current.clear()
    reconnectTimerRef.current.forEach(t => clearTimeout(t))
    reconnectTimerRef.current.clear()
    retryRef.current.clear()

    // Advance fetchMsgId so any in-flight fetchMessages will discard their result
    fetchMsgIdRef.current++

    // DON'T clear messages — keep old messages visible while new ones load.
    // fetchMessages will replace them when ready.

    // Sync ref immediately (don't wait for useEffect) to prevent race conditions
    // The useEffect on [activeThreadId] will call fetchMessages automatically
    switchThread(threadId)

    if (window.innerWidth < 768) setSidebarCollapsed(true)
  }

  const handleNewThread = async () => {
    // Abort any in-flight SSE chat stream
    if (chatAbortRef.current) {
      chatAbortRef.current.abort()
      chatAbortRef.current = null
    }
    // Close all video SSE connections
    esRef.current.forEach(es => es.close())
    esRef.current.clear()
    reconnectTimerRef.current.forEach(t => clearTimeout(t))
    reconnectTimerRef.current.clear()
    retryRef.current.clear()

    // Advance fetchMsgId so any in-flight fetchMessages discards its result
    fetchMsgIdRef.current++

    try {
      const res = await fetch(`/api/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ title: "新会话" }),
      })
      if (res.ok) {
        const data = await res.json()
        setThreads(prev => [data, ...prev])
        // Skip fetch — new thread is empty
        skipNextFetchRef.current = true
        setMessages([])
        switchThread(data.id)
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

  // ── Reference image (图生图 / 图生视频) helpers ──
  // Upload flow (per requirement): the selected image is first uploaded to a
  // dedicated MinIO bucket via /api/chat/upload; the returned same-origin proxy
  // URL is what we keep + send to the backend. The backend later inlines it as
  // base64 before calling the (remote) model, because the local MinIO URL is
  // not reachable by the model. Falls back to a local base64 data URL if the
  // upload endpoint is unavailable.
  const handleRefFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    const fileList = Array.from(files).slice(0, 8)
    const uploaded: string[] = []
    for (const file of fileList) {
      try {
        const fd = new FormData()
        fd.append("file", file)
        // IMPORTANT: do NOT pass authHeaders() here. authHeaders() sets
        // `Content-Type: application/json`, and if we send that with a FormData
        // body the browser won't add the multipart boundary — Starlette then
        // can't find the `file` part and returns HTTP 422. We only attach the
        // Authorization header and let the browser set the multipart Content-Type.
        const uploadHeaders: Record<string, string> = {}
        const upToken = getToken()
        if (upToken) uploadHeaders["Authorization"] = `Bearer ${upToken}`
        const res = await fetch("/api/chat/upload", {
          method: "POST",
          headers: uploadHeaders,
          body: fd,
        })
        if (res.ok) {
          const data = await res.json()
          if (data?.url) uploaded.push(data.url)
        } else {
          const dataUrl = await downscaleImage(file)
          if (dataUrl) uploaded.push(dataUrl)
        }
      } catch {
        const dataUrl = await downscaleImage(file)
        if (dataUrl) uploaded.push(dataUrl)
      }
    }
    if (uploaded.length) {
      setReferenceImages(prev => {
        const next = [...prev, ...uploaded].slice(0, 8)
        if (prev.length + uploaded.length > 8) message.info("最多支持 8 张参考图")
        return next
      })
    }
    e.target.value = ""
  }

  const removeRefImage = (idx: number) => {
    setReferenceImages(prev => prev.filter((_, i) => i !== idx))
  }

  // Turn any generated media URL into a reference image (inline same-origin
  // proxy URLs as data URLs; pass external URLs through for the backend).
  const useAsReference = async (url: string) => {
    if (!url) return
    try {
      if (url.startsWith("/api/")) {
        const resp = await fetch(url)
        if (resp.ok) {
          const blob = await resp.blob()
          const dataUrl = await new Promise<string>((resolve) => {
            const r = new FileReader()
            r.onload = () => resolve(r.result as string)
            r.readAsDataURL(blob)
          })
          setReferenceImages(prev => [...prev, dataUrl].slice(0, 8))
          message.success("已加入参考图")
          return
        }
      }
      setReferenceImages(prev => [...prev, url].slice(0, 8))
      message.success("已加入参考图")
    } catch {
      setReferenceImages(prev => [...prev, url].slice(0, 8))
      message.success("已加入参考图")
    }
  }

  // Copy a message's raw content to the clipboard (with fallback for
  // non-secure contexts where navigator.clipboard is unavailable).
  const copyMessage = async (content: string) => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(content)
      } else {
        const ta = document.createElement("textarea")
        ta.value = content
        ta.style.position = "fixed"
        ta.style.opacity = "0"
        document.body.appendChild(ta)
        ta.select()
        document.execCommand("copy")
        document.body.removeChild(ta)
      }
      message.success("已复制当前消息")
    } catch {
      message.error("复制失败，请手动选择文本复制")
    }
  }

  // Downscale a locally-selected image before base64-encoding it, so the
  // chat request body stays small (avoids the nginx 413 body-size limit and
  // speeds up transmission). Images already under maxDim pass through.
  const downscaleImage = (file: File, maxDim = 1280, quality = 0.85): Promise<string> =>
    new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = () => {
        const img = new Image()
        img.onload = () => {
          const { width, height } = img
          if (width <= maxDim && height <= maxDim) {
            resolve(reader.result as string)
            return
          }
          const scale = Math.min(maxDim / width, maxDim / height)
          const w = Math.round(width * scale)
          const h = Math.round(height * scale)
          const canvas = document.createElement("canvas")
          canvas.width = w
          canvas.height = h
          const ctx = canvas.getContext("2d")
          if (!ctx) { resolve(reader.result as string); return }
          ctx.drawImage(img, 0, 0, w, h)
          resolve(canvas.toDataURL("image/jpeg", quality))
        }
        img.onerror = () => resolve(reader.result as string)
        img.src = reader.result as string
      }
      reader.onerror = () => resolve("")
      reader.readAsDataURL(file)
    })

  // Small thumbnail row for reference images (removable when onRemove given).
  // Clicking a thumbnail opens the lightbox so the reference image can be viewed
  // full-size (the same viewer used for generated media).
  const renderRefThumbs = (urls: string[], onRemove?: (i: number) => void) =>
    urls.length === 0 ? null : (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
        {urls.map((u, i) => (
          <div key={i} style={{
            position: "relative", width: 56, height: 56, borderRadius: 8,
            overflow: "hidden", border: "1px solid var(--ice-border)", flexShrink: 0,
            cursor: "pointer", transition: "transform .2s ease",
          }}
            onClick={(e) => {
              // CRITICAL: stop bubbling — the parent container opens the
              // GENERATED image lightbox on click; without this the reference
              // thumbnail would wrongly show the generated image.
              e.stopPropagation()
              setLightboxState({
                images: urls.map((x) => ({ url: proxyMediaUrl(x), alt: "参考图" })),
                index: i,
              })
            }}
            onMouseEnter={(e) => (e.currentTarget.style.transform = "scale(1.08)")}
            onMouseLeave={(e) => (e.currentTarget.style.transform = "scale(1)")}
          >
            <img src={u} alt="参考图" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            {onRemove && (
              <span
                onClick={(e) => { e.stopPropagation(); onRemove(i) }}
                style={{
                  position: "absolute", top: 2, right: 2, width: 18, height: 18,
                  borderRadius: "50%", background: "rgba(0,0,0,0.6)", color: "#fff",
                  fontSize: 12, lineHeight: "18px", textAlign: "center", cursor: "pointer",
                }}
              >×</span>
            )}
          </div>
        ))}
      </div>
    )

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
                destroyPopupOnHide
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
                    <Popconfirm
                      title="删除会话"
                      description="该会话及其消息将被永久删除，且无法恢复。"
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => deleteThread(t.id)}
                    >
                      <Button
                        type="text"
                        danger
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={e => e.stopPropagation()}
                        style={{ opacity: 0.5, flexShrink: 0 }}
                        onMouseEnter={e => ((e.currentTarget as HTMLButtonElement).style.opacity = "1")}
                        onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.opacity = "0.5")}
                      />
                    </Popconfirm>
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
        <div
          ref={scrollRef}
          onScroll={handleMessagesScroll}
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "20px 24px",
            background: "var(--ice-bg-primary)",
            position: "relative",
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
            <div style={{
              position: "relative",
            }}>
              {/* History loading indicator — appears at the top while the user
                  scrolls up to load older messages. */}
              {loadingHistory && (
                <div style={{
                  textAlign: "center", padding: "6px 0 12px",
                  color: "var(--ice-text-muted)", fontSize: 12,
                }}>
                  加载历史消息…
                </div>
              )}
              {!hasMoreHistory && !loadingHistory && (
                <div style={{
                  textAlign: "center", padding: "6px 0 12px",
                  color: "var(--ice-text-muted)", fontSize: 12, opacity: 0.7,
                }}>
                  没有更早的消息了
                </div>
              )}
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
                    }}
                      className="msg-bubble"
                    >
                      {/* Hover-to-copy button for this message */}
                      <Button
                        className="msg-copy-btn"
                        type="text"
                        size="small"
                        icon={<CopyOutlined />}
                        title="复制当前消息"
                        onClick={(e) => {
                          e.stopPropagation()
                          copyMessage(msg.content)
                        }}
                        style={{
                          position: "absolute",
                          top: 4,
                          right: 4,
                          width: 26,
                          height: 26,
                          padding: 0,
                          color: "var(--ice-text-muted)",
                          background: msg.role === "user" ? "rgba(255,255,255,0.6)" : "var(--ice-bg-secondary)",
                          zIndex: 5,
                        }}
                      />
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
                                    { url: proxyMediaUrl(msg.blocks.image_url), alt: "生成图片" },
                                    ...(msg.blocks.images?.map((img) => ({
                                      url: proxyMediaUrl(img.url),
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
                                onUseAsReference={
                                  msg.blocks?.type === "image" && msg.blocks?.image_url
                                    ? () => useAsReference(msg.blocks!.image_url!)
                                    : undefined
                                }
                                onContentLoaded={() => {
                                  // Keep the view pinned to the bottom only if the
                                  // user is already there (don't yank them out of
                                  // history they're reading when an image loads).
                                  if (atBottomRef.current && scrollRef.current) {
                                    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
                                  }
                                }}
                                onThumbnailClick={(index) => {
                                  if (msg.blocks?.type === "image" && msg.blocks.image_url) {
                                    const allImages: LightboxImage[] = [
                                      { url: proxyMediaUrl(msg.blocks.image_url), alt: "生成图片" },
                                      ...(msg.blocks.images?.map((img) => ({
                                        url: proxyMediaUrl(img.url),
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
                              {msg.blocks.reference_images && msg.blocks.reference_images.length > 0 && (
                                <div style={{ marginTop: 8 }}>
                                  <div style={{ fontSize: 11, color: "var(--ice-text-muted)", marginBottom: 4 }}>
                                    参考图
                                  </div>
                                  {renderRefThumbs(msg.blocks.reference_images)}
                                  {/* Video messages have no in-card action bar, so keep
                                      the "用作参考图" button here for them. Image messages
                                      get it in the MediaCard action bar (after 复制链接). */}
                                  {msg.blocks.type === "video" && (
                                    <div style={{ marginTop: 8 }}>
                                      <Button
                                        size="small"
                                        icon={<PictureOutlined />}
                                        disabled={!msg.blocks?.video_url}
                                        onClick={() => useAsReference(msg.blocks?.video_url || "")}
                                      >
                                        用作参考图
                                      </Button>
                                    </div>
                                  )}
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
                        <div>
                          <Text style={{
                            color: "var(--ice-text-primary)",
                            fontSize: 14,
                            lineHeight: 1.7,
                            whiteSpace: "pre-wrap",
                          }}>
                            {msg.content}
                          </Text>
                          {msg.blocks?.reference_images && msg.blocks.reference_images.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                              <div style={{ fontSize: 11, color: "var(--ice-text-muted)", marginBottom: 4 }}>
                                参考图
                              </div>
                              {renderRefThumbs(msg.blocks.reference_images)}
                            </div>
                          )}
                        </div>
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

            {activeTemplate && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: "#888" }}>已选模板:</span>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 12,
                    color: primaryColor,
                    background: `${primaryColor}14`,
                    padding: "2px 8px",
                    borderRadius: 12,
                  }}
                >
                  {activeTemplate.name}
                  <span
                    style={{ cursor: "pointer", fontWeight: 700, lineHeight: 1 }}
                    title="清除模板"
                    onClick={() => setTemplateId(null)}
                  >
                    ×
                  </span>
                </span>
              </div>
            )}

            {referenceImages.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>
                  参考图（图生图 / 图生视频）· {referenceImages.length}/8
                </div>
                {renderRefThumbs(referenceImages, removeRefImage)}
              </div>
            )}

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
              <Tooltip title="添加参考图（图生图 / 图生视频）">
                <Button
                  icon={<PictureOutlined />}
                  onClick={() => refInputRef.current?.click()}
                  style={{ borderRadius: 8 }}
                />
              </Tooltip>
              {(modelType === 'image' || modelType === 'video') && (
                <Tooltip title="高级参数（图片尺寸 / 视频时长）">
                  <Button
                    icon={<ControlOutlined />}
                    type={advancedOpen ? "primary" : "default"}
                    onClick={() => setAdvancedOpen(o => !o)}
                    style={{ borderRadius: 8 }}
                  />
                </Tooltip>
              )}
              <ChatSelector
                providerId={providerId}
                providerType={providerType}
                modelName={modelName}
                modelType={modelType}
                templateId={templateId}
                templates={templates}
                onProviderChange={(pid, mname, ptype, mtype) => setProviderAndModel(pid, mname, ptype, mtype)}
                onTemplateChange={handleTemplateChange}
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

            {advancedOpen && (modelType === 'image' || modelType === 'video') && (
              <div style={{ display: "flex", gap: 12, marginTop: 10, flexWrap: "wrap" }}>
                {/* 图片模型：仅显示尺寸参数，不显示视频时长 */}
                {modelType === 'image' && (
                  <Select
                    value={genSize}
                    onChange={(v) => { setGenSize(v); userPickedSizeRef.current = true }}
                    style={{ width: 160 }}
                    size="small"
                    options={[
                      { value: "1024x1024", label: "方图 1024×1024" },
                      { value: "1024x768", label: "横图 1024×768" },
                      { value: "768x1024", label: "竖图 768×1024" },
                      { value: "512x512", label: "小图 512×512" },
                    ]}
                  />
                )}
                {/* 视频模型：仅显示时长参数，不显示图片尺寸 */}
                {modelType === 'video' && (
                  <Select
                    value={genDuration}
                    onChange={(v) => setGenDuration(Number(v))}
                    style={{ width: 130 }}
                    size="small"
                    options={[
                      { value: 3, label: "视频 3 秒" },
                      { value: 5, label: "视频 5 秒" },
                      { value: 10, label: "视频 10 秒" },
                    ]}
                  />
                )}
              </div>
            )}

            <input
              ref={refInputRef}
              type="file"
              accept="image/*"
              multiple
              style={{ display: "none" }}
              onChange={handleRefFiles}
            />
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

      {/* Pulse + spin animations */}
      <style>{`
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        /* Hover-to-copy button on each chat bubble */
        .msg-bubble {
          position: relative;
        }
        .msg-bubble .msg-copy-btn {
          opacity: 0;
          transition: opacity 0.15s ease;
          pointer-events: none;
        }
        .msg-bubble:hover .msg-copy-btn {
          opacity: 1;
          pointer-events: auto;
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
