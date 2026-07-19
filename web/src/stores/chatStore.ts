import { create } from "zustand"

export interface ChatMessage {
  id: number
  role: string
  content: string
  created_at?: string
  blocks?: any
  [key: string]: any
}

interface ChatStoreState {
  /** threadId -> messages, kept in memory for the whole session. */
  byThread: Record<string, ChatMessage[]>
  /** Replace a thread's messages (e.g. after loading from DB). */
  setMessages: (threadId: string, msgs: ChatMessage[]) => void
  /** Append a message to a thread (user msg or a new assistant bubble). */
  appendMessage: (threadId: string, msg: ChatMessage) => void
  /** Overwrite the last assistant message's content + blocks (finalize). */
  updateLastAssistant: (threadId: string, content: string, blocks?: any) => void
  /** Append a streaming delta to the last assistant message (typewriter). */
  appendToLastAssistant: (threadId: string, delta: string) => void
  /** Read cached messages for a thread (instant hydrate on page switch). */
  getMessages: (threadId: string) => ChatMessage[] | undefined
  /** Drop a thread's cache (e.g. after hard delete). */
  clear: (threadId: string) => void
}

export const useChatStore = create<ChatStoreState>((set, get) => ({
  byThread: {},
  setMessages: (threadId, msgs) =>
    set((s) => ({ byThread: { ...s.byThread, [threadId]: msgs } })),
  appendMessage: (threadId, msg) =>
    set((s) => ({
      byThread: { ...s.byThread, [threadId]: [...(s.byThread[threadId] || []), msg] },
    })),
  updateLastAssistant: (threadId, content, blocks) =>
    set((s) => {
      const arr = s.byThread[threadId]
      if (!arr || !arr.length) return {}
      const copy = arr.slice()
      const last = copy[copy.length - 1]
      copy[copy.length - 1] = { ...last, content, blocks: blocks ?? last.blocks }
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
}))
