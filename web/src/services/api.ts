export interface KnowledgeBase {
  id: number
  name: string
  description: string
  embedding_model: string
  chunk_size: number
  chunk_overlap: number
  enabled: boolean
  created_at: string
}

export interface KBFolder {
  id: number
  name: string
  description: string
  parent_id: number | null
  children: KBFolder[]
  document_count: number
}

export interface KBDocument {
  id: number
  kb_id: number
  folder_id: number | null
  original_filename: string
  file_type: string
  file_size: number
  status: 'pending' | 'processing' | 'ready' | 'failed'
  error_message: string | null
  created_at: string
}

export interface KBSearchResult {
  chunk_id: number
  vector_id: string
  document_id: number
  document_name: string
  folder_path: string
  page_number: number | null
  chunk_index: number
  content: string
  score: number
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('agent-token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export const kbApi = {
  list: () => fetch('/api/knowledge-bases', { headers: authHeaders() }).then(r => r.json()),
  create: (data: Partial<KnowledgeBase>) =>
    fetch('/api/knowledge-bases', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  update: (id: number, data: Partial<KnowledgeBase>) =>
    fetch(`/api/knowledge-bases/${id}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  remove: (id: number) => fetch(`/api/knowledge-bases/${id}`, { method: 'DELETE', headers: authHeaders() }),
  getFolders: (kbId: number) =>
    fetch(`/api/knowledge-bases/${kbId}/folders/tree`, { headers: authHeaders() }).then(r => r.json()),
  createFolder: (kbId: number, data: { name: string; parent_id?: number }) =>
    fetch(`/api/knowledge-bases/${kbId}/folders`, { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  listDocuments: (kbId: number, folderId?: number) => {
    const url = folderId ? `/api/knowledge-bases/${kbId}/documents?folder_id=${folderId}` : `/api/knowledge-bases/${kbId}/documents`
    return fetch(url, { headers: authHeaders() }).then(r => r.json())
  },
  uploadFile: (kbId: number, file: File, folderId?: number) => {
    const fd = new FormData()
    fd.append('file', file)
    if (folderId) fd.append('folder_id', String(folderId))
    return fetch(`/api/knowledge-bases/${kbId}/upload`, { method: 'POST', headers: authHeaders(), body: fd })
      .then(r => r.json())
  },
  deleteDocument: (kbId: number, docId: number) =>
    fetch(`/api/knowledge-bases/${kbId}/documents/${docId}`, { method: 'DELETE', headers: authHeaders() }),
  search: (kbId: number, query: string, topK: number = 5) =>
    fetch('/api/knowledge-bases/search', {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ kb_id: kbId, query, top_k: topK }),
    }).then(r => r.json()),
  getStats: (kbId: number) =>
    fetch(`/api/knowledge-bases/${kbId}/stats`, { headers: authHeaders() }).then(r => r.json()).catch(() => null),
}

export const userApi = {
  list: () => fetch('/api/users', { headers: authHeaders() }).then(r => r.json()),
  update: (id: number, data: { role?: string; enabled?: boolean }) =>
    fetch(`/api/users/${id}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  remove: (id: number) => fetch(`/api/users/${id}`, { method: 'DELETE', headers: authHeaders() }),
}

export const settingsApi = {
  list: () => fetch('/api/settings', { headers: authHeaders() }).then(r => r.json()),
  create: (data: { key: string; value: string; description?: string }) =>
    fetch('/api/settings', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  update: (key: string, data: { value: string }) =>
    fetch(`/api/settings/${key}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  remove: (key: string) => fetch(`/api/settings/${key}`, { method: 'DELETE', headers: authHeaders() }),
}

export const mcpApi = {
  list: () => fetch('/api/mcp-servers', { headers: authHeaders() }).then(r => r.json()),
  create: (data: any) => fetch('/api/mcp-servers', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  update: (id: number, data: any) => fetch(`/api/mcp-servers/${id}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  remove: (id: number) => fetch(`/api/mcp-servers/${id}`, { method: 'DELETE', headers: authHeaders() }),
}

export const skillApi = {
  list: () => fetch('/api/skills', { headers: authHeaders() }).then(r => r.json()),
  create: (data: any) => fetch('/api/skills', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  update: (id: number, data: any) => fetch(`/api/skills/${id}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  remove: (id: number) => fetch(`/api/skills/${id}`, { method: 'DELETE', headers: authHeaders() }),
}
