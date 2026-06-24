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

export const agentApi = {
  list: () => fetch('/api/agents', { headers: authHeaders() }).then(r => r.json()),
  create: (data: AgentCreate) => postJson('/api/agents', data),
  update: (id: number, data: Partial<AgentCreate>) => patchJson(`/api/agents/${id}`, data),
  remove: (id: number) => fetch(`/api/agents/${id}`, { method: 'DELETE', headers: authHeaders() }),
  chat: (agentId: number, message: string, threadId?: string) =>
    postJson('/api/chat', { agent_id: agentId, message, thread_id: threadId }),
  getThreads: (agentId: number) =>
    fetch(`/api/agents/${agentId}/threads`, { headers: authHeaders() }).then(r => r.json()),
  createThread: (agentId: number, title?: string) =>
    postJson(`/api/agents/${agentId}/threads`, { title: title || 'New chat' }),
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('agent-token')
  return token ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } : { 'Content-Type': 'application/json' }
}

function postJson(url: string, body: any) {
  return fetch(url, { method: 'POST', headers: authHeaders(), body: JSON.stringify(body) }).then(r => r.json())
}

function patchJson(url: string, body: any) {
  return fetch(url, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify(body) }).then(r => r.json())
}
