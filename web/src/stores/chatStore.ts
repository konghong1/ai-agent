import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

export interface ChatMessage {
  id: number
  role: string
  content: string
  created_at?: string
  blocks?: any
  pending?: boolean
  /** 用户主动点「停止生成」提前结束（低调灰色提示，非错误）。 */
  stopped?: boolean
  /** 真实错误（网络/后端失败）导致的回复中断（红色提示）。 */
  interrupted?: boolean
  [key: string]: any
}

// localStorage 容量上限约 5MB。历史消息若全量持久化，多个会话（尤其是含
// 图片/视频的会话）叠加极易超出配额，抛出
// "Failed to execute 'setItem' ... exceeded the quota" 并使页面在加载时崩溃。
// 因此持久化时只保留「当前活跃会话」的最近 N 条，后端 DB 才是完整数据源，
// 缓存仅用于在切换/刷新后做瞬时首屏渲染，随后由 fetchLatest 用 DB 数据覆盖。
const MAX_MSGS_PER_THREAD = 50
const MAX_CONTENT_LEN = 30000 // 单条消息内容安全上限，避免个别超长消息撑爆配额

/** 把单会话消息裁剪为可持久化的大小（最近 N 条 + 超长内容截断）。 */
function boundMessages(msgs: ChatMessage[] | undefined): ChatMessage[] {
  if (!Array.isArray(msgs)) return []
  const recent = msgs.slice(-MAX_MSGS_PER_THREAD)
  return recent.map((m) => {
    if (m.content && m.content.length > MAX_CONTENT_LEN) {
      return { ...m, content: m.content.slice(0, MAX_CONTENT_LEN) }
    }
    return m
  })
}

// 永不抛异常的 localStorage 包装。当序列化后超出配额（或处于隐私模式）时，
// 直接丢弃缓存而非让整个应用崩溃——数据会在下次 fetch 时从后端重新加载。
const safeLocalStorage = {
  getItem: (name: string): string | null => {
    try {
      return localStorage.getItem(name)
    } catch {
      return null
    }
  },
  setItem: (name: string, value: string): void => {
    try {
      localStorage.setItem(name, value)
    } catch {
      // 配额超限：清空后重试一次（留下空缓存），最坏情况也只是丢失缓存，
      // 不会阻塞应用。DB 会在挂载时重新拉取完整消息。
      try {
        localStorage.removeItem(name)
      } catch {
        /* ignore */
      }
    }
  },
  removeItem: (name: string): void => {
    try {
      localStorage.removeItem(name)
    } catch {
      /* ignore */
    }
  },
}

interface ChatStoreState {
  /** threadId -> messages, kept in memory for the whole session. */
  byThread: Record<string, ChatMessage[]>
  /** 当前活跃会话 id（持久化，用于决定缓存哪一份历史）。 */
  activeThreadId: string | null
  /** 标记当前活跃会话（由 ChatInterface 在切换会话时调用）。 */
  setActiveThreadId: (threadId: string | null) => void
  /** Replace a thread's messages (e.g. after loading from DB). */
  setMessages: (threadId: string, msgs: ChatMessage[]) => void
  /** Append a message to a thread (user msg or a new assistant bubble). */
  appendMessage: (threadId: string, msg: ChatMessage) => void
  /** Overwrite the last assistant message's content + blocks (finalize). */
  updateLastAssistant: (threadId: string, content: string, blocks?: any, extra?: Partial<ChatMessage>) => void
  /** Append a streaming delta to the last assistant message (typewriter). */
  appendToLastAssistant: (threadId: string, delta: string) => void
  /** Read cached messages for a thread (instant hydrate on page switch). */
  getMessages: (threadId: string) => ChatMessage[] | undefined
  /** Drop a thread's cache (e.g. after hard delete). */
  clear: (threadId: string) => void
  /** Thread ids that currently have an in-flight SSE stream (ephemeral, not persisted). */
  streamingThreadIds: string[]
  /** Mark/unmark a thread as having an active stream (drives the 停止生成 button). */
  setStreamingThread: (threadId: string, on: boolean) => void
}

export const useChatStore = create<ChatStoreState>()(
  persist(
    (set, get) => ({
      byThread: {},
      activeThreadId: null,
      setActiveThreadId: (threadId) => set({ activeThreadId: threadId }),
      setMessages: (threadId, msgs) =>
        set((s) => ({ byThread: { ...s.byThread, [threadId]: msgs } })),
      appendMessage: (threadId, msg) =>
        set((s) => ({
          byThread: { ...s.byThread, [threadId]: [...(s.byThread[threadId] || []), msg] },
        })),
      updateLastAssistant: (threadId, content, blocks, extra) =>
        set((s) => {
          const arr = s.byThread[threadId]
          if (!arr || !arr.length) return {}
          const copy = arr.slice()
          const last = copy[copy.length - 1]
          copy[copy.length - 1] = {
            ...last,
            content,
            blocks: blocks ?? last.blocks,
            ...(extra || {}),
          }
          return { byThread: { ...s.byThread, [threadId]: copy } }
        }),
      appendToLastAssistant: (threadId, delta) =>
        set((s) => {
          const arr = s.byThread[threadId]
          if (!arr || !arr.length) return {}
          const copy = arr.slice()
          const last = copy[copy.length - 1]
          copy[copy.length - 1] = { ...last, content: (last.content || "") + delta }
          return { byThread: { ...s.byThread, [threadId]: copy } }
        }),
      getMessages: (threadId) => get().byThread[threadId],
      clear: (threadId) =>
        set((s) => {
          const next = { ...s.byThread }
          delete next[threadId]
          return { byThread: next }
        }),
      streamingThreadIds: [],
      setStreamingThread: (threadId, on) =>
        set((s) => {
          const has = s.streamingThreadIds.includes(threadId)
          if (on && !has) return { streamingThreadIds: [...s.streamingThreadIds, threadId] }
          if (!on && has) return { streamingThreadIds: s.streamingThreadIds.filter((t) => t !== threadId) }
          return {}
        }),
    }),
    {
      name: "chat-messages-cache",
      storage: createJSONStorage(() => safeLocalStorage),
      // 只持久化当前活跃会话的最近若干条消息，避免所有会话历史堆积撑爆配额。
      // streamingThreadIds 是易失状态，绝不持久化（reload 后残留的 true 会
      // 错误显示「停止生成」按钮）。
      partialize: (s) => {
        const active = s.activeThreadId
        const activeMsgs = active ? s.byThread[active] : undefined
        return {
          activeThreadId: active,
          byThread: active && activeMsgs ? { [active]: boundMessages(activeMsgs) } : {},
        }
      },
    }
  )
)
