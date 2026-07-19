import { request } from './request'

export interface MemoryItem {
  id: number
  user_id: number
  layer: number
  mem_type: string
  key: string
  value: string
  importance: number
  confidence: number
  status: string
  source: string
  created_at: string | null
  updated_at: string | null
}

export interface PendingItem {
  id: number
  user_id: number
  candidate: string
  status: string
  created_at: string | null
}

export interface MemoryPreview {
  // 后端 preview_memory 返回 标签->文本 的字典（core / reflex / recall / gap ...）
  [label: string]: string
}

export interface MemoryCreatePayload {
  key: string
  value: string
  layer?: number
  mem_type?: string
  importance?: number
  confidence?: number
}

export interface MemoryUpdatePayload {
  key?: string
  value?: string
  layer?: number
  mem_type?: string
  importance?: number
  confidence?: number
}

export const memoryApi = {
  list: () => request<MemoryItem[]>('/api/memories'),

  create: (data: MemoryCreatePayload) =>
    request<MemoryItem>('/api/memories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  update: (id: number, data: MemoryUpdatePayload) =>
    request<MemoryItem>(`/api/memories/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  remove: (id: number) =>
    request<{ status: string }>(`/api/memories/${id}`, { method: 'DELETE' }),

  listPending: () => request<PendingItem[]>('/api/memories/pending'),

  acceptPending: (id: number) =>
    request<MemoryItem>(`/api/memories/pending/${id}/accept`, { method: 'POST' }),

  rejectPending: (id: number) =>
    request<{ status: string }>(`/api/memories/pending/${id}/reject`, { method: 'POST' }),

  preview: (text: string) =>
    request<MemoryPreview>(`/api/memories/preview?text=${encodeURIComponent(text)}`),
}
