export interface Agent {
  id: number
  name: string
  description: string
  system_prompt: string
  model_provider: string
  model_name: string
  temperature: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface AgentCreate {
  name: string
  description?: string
  system_prompt?: string
  model_name?: string
  temperature?: number
  enabled?: boolean
  knowledge_base_ids?: number[]
}

import { authHeaders, getToken } from './auth'

export const agentApi = {
  list: () => fetch('/api/agents', { headers: authHeaders() }).then(r => r.json()),
  create: (data: AgentCreate) =>
    fetch('/api/agents', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  update: (id: number, data: Partial<AgentCreate>) =>
    fetch(`/api/agents/${id}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  remove: (id: number) => fetch(`/api/agents/${id}`, { method: 'DELETE', headers: authHeaders() }),
  chat: (agentId: number, message: string, threadId?: string) =>
    fetch('/api/chat', {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId, message, thread_id: threadId }),
    }).then(r => r.json()),
  getThreads: (agentId: number) =>
    fetch(`/api/agents/${agentId}/threads`, { headers: authHeaders() }).then(r => r.json()),
  createThread: (agentId: number, title?: string) =>
    fetch(`/api/agents/${agentId}/threads`, {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title || 'New chat' }),
    }).then(r => r.json()),
}
