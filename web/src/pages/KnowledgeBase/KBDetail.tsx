import { useEffect, useState, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  PlusOutlined, UploadOutlined, SearchOutlined, DeleteOutlined,
  FileTextOutlined, EyeOutlined, ReloadOutlined, BookOutlined,
  BarChartOutlined, SettingOutlined, FolderOutlined, SaveOutlined,
} from '@ant-design/icons'
import { Form, Input, Button, Select, Modal, message, InputNumber } from 'antd'
import { authHeaders } from '@/services/auth'
import './kb-styles.css'

// ---------- Types ----------
interface KBFolder {
  id: number
  name: string
  parent_id: number | null
  children: KBFolder[]
  document_count: number
}
interface KBDoc {
  id: number
  original_filename: string
  file_type: string
  file_size: number
  status: string
  error_message: string | null
  created_at: string
  folder_id: number | null
}
interface KB {
  id: number
  name: string
  description: string
  enabled: boolean
  chunk_size: number
  chunk_overlap: number
  embedding_model: string
  created_at: string
  updated_at: string
}
interface SearchResult {
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

// ---------- Helpers ----------
const CHUNKING_LABELS: Record<string, string> = {
  recursive_character: '递归字符分块（推荐）',
  fixed_size: '固定大小分块',
  hierarchical: '文档结构分块',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

function getFileTypeIcon(fileType: string): { cls: string; label: string } {
  const t = (fileType || '').toLowerCase()
  if (t.includes('pdf')) return { cls: 'file-type-pdf', label: 'PDF' }
  if (t.includes('doc') || t.includes('word')) return { cls: 'file-type-doc', label: 'DOC' }
  if (t.includes('md') || t.includes('markdown')) return { cls: 'file-type-md', label: 'MD' }
  if (t.includes('txt')) return { cls: 'file-type-txt', label: 'TXT' }
  if (t.includes('py') || t.includes('js') || t.includes('ts') || t.includes('code') || t.includes('json') || t.includes('csv'))
    return { cls: 'file-type-code', label: t.slice(0, 3).toUpperCase() || 'CODE' }
  return { cls: 'file-type-txt', label: 'FILE' }
}

/** Map document status to pipeline steps */
function getPipelineSteps(status: string): ('done' | 'active' | 'failed' | 'pending')[] {
  // Pipeline: extract -> clean -> chunk -> embed -> store
  switch (status) {
    case 'ready': return ['done', 'done', 'done', 'done', 'done']
    case 'processing': return ['done', 'done', 'done', 'active', 'pending']
    case 'failed': return ['done', 'done', 'failed', 'pending', 'pending']
    case 'pending': return ['pending', 'pending', 'pending', 'pending', 'pending']
    default: return ['pending', 'pending', 'pending', 'pending', 'pending']
  }
}

function flattenFolders(folders: KBFolder[]): KBFolder[] {
  const result: KBFolder[] = []
  const walk = (items: KBFolder[]) =>
    items.forEach((f) => { result.push(f); f.children && walk(f.children) })
  walk(folders)
  return result
}

// ---------- Toggle Component ----------
function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <div
      className={`kb-toggle ${on ? 'on' : ''}`}
      onClick={(e) => { e.stopPropagation(); onClick() }}
    />
  )
}

// ---------- Main Component ----------
export default function KBDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [kb, setKb] = useState<KB | null>(null)
  const [folders, setFolders] = useState<KBFolder[]>([])
  const [activeFolderId, setActiveFolderId] = useState<number | null>(null)
  const [documents, setDocuments] = useState<KBDoc[]>([])
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeTab, setActiveTab] = useState<'docs' | 'search' | 'stats' | 'config'>('docs')
  const [uploadModal, setUploadModal] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedFolder, setSelectedFolder] = useState<number | null>(null)
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [folderModal, setFolderModal] = useState(false)
  const [form] = Form.useForm()
  const [searchParams, setSearchParams] = useState({ topK: 5, rerank: true })
  const [searchMeta, setSearchMeta] = useState<{ time: number; tokens: number } | null>(null)
  const [feedback, setFeedback] = useState<Record<number, 'up' | 'down'>>({})

  // RAG config state
  const [ragConfig, setRagConfig] = useState({
    hybridSearch: true,
    queryRewrite: true,
    topK: 20,
    minScore: 0.3,
    rerankEnabled: true,
    rerankModel: 'bge-reranker-base',
    rerankTopN: 10,
    mmrEnabled: true,
    mmrThreshold: 0.5,
    maxContextTokens: 4000,
    citeSource: true,
    sourceFormat: '[来源: 文件名, 相关度: X%]',
    chunkStrategy: 'recursive_character',
    chunkSize: 500,
    chunkOverlap: 50,
    minChunkSize: 50,
  })

  useEffect(() => {
    if (!id) return
    Promise.all([
      fetch('/api/knowledge-bases/' + id, { headers: authHeaders() }).then((r) => r.json()),
      fetch('/api/knowledge-bases/' + id + '/folders/tree', { headers: authHeaders() }).then((r) => r.json()),
      fetch('/api/knowledge-bases/' + id + '/documents', { headers: authHeaders() }).then((r) => r.json()),
    ]).then(([kbData, folderData, docData]) => {
      setKb(kbData)
      setFolders(folderData)
      setDocuments(docData)
      // Initialize RAG config from KB data
      if (kbData.chunk_size) setRagConfig((p) => ({ ...p, chunkSize: kbData.chunk_size, chunkOverlap: kbData.chunk_overlap }))
    })
  }, [id])

  const pollStatus = useCallback(
    (docId: number) => {
      const interval = setInterval(async () => {
        try {
          const res = await fetch('/api/knowledge-bases/' + id + '/documents', { headers: authHeaders() })
          const docs = await res.json()
          const doc = docs.find((d: KBDoc) => d.id === docId)
          if (doc && ['ready', 'failed'].includes(doc.status)) {
            clearInterval(interval)
            setDocuments(docs)
            if (doc.status === 'ready') message.success('文档处理完成')
            else message.error('处理失败: ' + (doc.error_message || '未知错误'))
          }
        } catch { /* ignore */ }
      }, 2000)
      return () => clearInterval(interval)
    },
    [id]
  )

  const handleUpload = async () => {
    if (!uploadedFiles.length) return
    setUploading(true)
    for (const file of uploadedFiles) {
      const fd = new FormData()
      fd.append('file', file)
      if (selectedFolder) fd.append('folder_id', String(selectedFolder))
      try {
        const res = await fetch('/api/knowledge-bases/' + id + '/upload', {
          method: 'POST',
          headers: authHeaders(),
          body: fd,
        })
        const data = await res.json()
        pollStatus(data.document_id)
      } catch (e: any) {
        message.error(e.message)
      }
    }
    setUploading(false)
    setUploadModal(false)
    setUploadedFiles([])
    message.success('文件已上传，正在处理中...')
    // Refresh document list
    setTimeout(() => {
      fetch('/api/knowledge-bases/' + id + '/documents', { headers: authHeaders() })
        .then((r) => r.json())
        .then(setDocuments)
    }, 1000)
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearchLoading(true)
    setSearchMeta(null)
    const startTime = Date.now()
    try {
      const res = await fetch('/api/knowledge-bases/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          kb_id: Number(id),
          query: searchQuery,
          top_k: searchParams.topK,
          folder_id: activeFolderId,
        }),
      })
      const data = await res.json()
      setSearchResults(data)
      setSearchMeta({ time: Date.now() - startTime, tokens: data.reduce((s: number, r: SearchResult) => s + Math.ceil(r.content.length / 4), 0) })
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setSearchLoading(false)
    }
  }

  const handleDeleteDoc = async (docId: number) => {
    await fetch('/api/knowledge-bases/' + id + '/documents/' + docId, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    setDocuments((prev) => prev.filter((d) => d.id !== docId))
    message.success('已删除')
  }

  const handleSaveRagConfig = async () => {
    try {
      const res = await fetch(`/api/knowledge-bases/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          chunk_size: ragConfig.chunkSize,
          chunk_overlap: ragConfig.chunkOverlap,
        }),
      })
      if (!res.ok) throw new Error('保存失败')
      message.success('RAG 配置已保存')
    } catch (e: any) {
      message.error(e.message)
    }
  }

  // Filter documents by active folder
  const filteredDocs = useMemo(() => {
    if (activeFolderId === null) return documents
    return documents.filter((d) => d.folder_id === activeFolderId)
  }, [documents, activeFolderId])

  // Stats calculations
  const stats = useMemo(() => {
    const ready = documents.filter((d) => d.status === 'ready').length
    const processing = documents.filter((d) => d.status === 'processing').length
    const failed = documents.filter((d) => d.status === 'failed').length
    const pending = documents.filter((d) => d.status === 'pending').length
    return { total: documents.length, ready, processing, failed, pending }
  }, [documents])

  // ---------- Render ----------
  return (
    <div className="kb-detail-page">
      {/* Breadcrumb */}
      <div className="kb-breadcrumb">
        <a onClick={() => navigate('/knowledge-bases')}>知识库</a>
        <span>/</span>
        <span style={{ color: 'var(--ice-text-primary)' }}>{kb?.name || '...'}</span>
      </div>

      {/* Detail Header */}
      <div className="detail-header">
        <div className="detail-header-left">
          <div className="detail-header-icon">
            <BookOutlined />
          </div>
          <div>
            <h2>{kb?.name || '加载中...'}</h2>
            <div className="desc">{kb?.description || '暂无描述'}</div>
            <div className="detail-header-tags">
              <span className="kb-tag kb-tag-cyan">{kb?.embedding_model || 'text-embedding-3-small'}</span>
              {ragConfig.hybridSearch && <span className="kb-tag kb-tag-green">混合检索</span>}
              {ragConfig.rerankEnabled && <span className="kb-tag kb-tag-green">重排序已启用</span>}
              {ragConfig.mmrEnabled && <span className="kb-tag kb-tag-purple">MMR 去重</span>}
              <span className="kb-tag kb-tag-gray">Chunk: {kb?.chunk_size || 500} / Overlap: {kb?.chunk_overlap || 50}</span>
            </div>
          </div>
        </div>
        <div className="detail-header-right">
          <Button icon={<SettingOutlined />} onClick={() => setActiveTab('config')}>编辑</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadModal(true)}>上传文档</Button>
        </div>
      </div>

      {/* Detail Layout */}
      <div className="detail-layout">
        {/* Folder Sidebar */}
        <div className="folder-sidebar">
          <div className="folder-sidebar-header">
            <span className="folder-sidebar-title">文件夹</span>
            <button className="kb-btn-icon" onClick={() => setFolderModal(true)} title="新建文件夹">
              <PlusOutlined />
            </button>
          </div>
          <div className="folder-tree">
            <div
              className={`folder-item ${activeFolderId === null ? 'active' : ''}`}
              onClick={() => setActiveFolderId(null)}
            >
              <FolderOutlined className="folder-icon" />
              <span className="folder-name">全部文档</span>
              <span className="folder-count">{documents.length}</span>
            </div>
            {folders.map((f) => (
              <div key={f.id}>
                <div
                  className={`folder-item ${activeFolderId === f.id ? 'active' : ''}`}
                  onClick={() => setActiveFolderId(f.id)}
                >
                  <FolderOutlined className="folder-icon" />
                  <span className="folder-name">{f.name}</span>
                  <span className="folder-count">{f.document_count}</span>
                </div>
                {f.children && f.children.length > 0 && (
                  <div className="folder-children">
                    {f.children.map((c) => (
                      <div
                        key={c.id}
                        className={`folder-item ${activeFolderId === c.id ? 'active' : ''}`}
                        onClick={() => setActiveFolderId(c.id)}
                      >
                        <FolderOutlined className="folder-icon" />
                        <span className="folder-name">{c.name}</span>
                        <span className="folder-count">{c.document_count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Main Content */}
        <div className="detail-main">
          {/* Tab Bar */}
          <div className="kb-tab-bar">
            <div
              className={`kb-tab-item ${activeTab === 'docs' ? 'active' : ''}`}
              onClick={() => setActiveTab('docs')}
            >
              <FileTextOutlined /> 文档管理
            </div>
            <div
              className={`kb-tab-item ${activeTab === 'search' ? 'active' : ''}`}
              onClick={() => setActiveTab('search')}
            >
              <SearchOutlined /> 检索测试
            </div>
            <div
              className={`kb-tab-item ${activeTab === 'stats' ? 'active' : ''}`}
              onClick={() => setActiveTab('stats')}
            >
              <BarChartOutlined /> 统计分析
            </div>
            <div
              className={`kb-tab-item ${activeTab === 'config' ? 'active' : ''}`}
              onClick={() => setActiveTab('config')}
            >
              <SettingOutlined /> RAG 配置
            </div>
          </div>

          {/* ===== Documents Tab ===== */}
          {activeTab === 'docs' && (
            <div>
              <div className="doc-toolbar">
                <div className="doc-toolbar-left">
                  <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadModal(true)}>
                    上传文件
                  </Button>
                  <Select
                    placeholder="选择文件夹"
                    value={selectedFolder || undefined}
                    onChange={setSelectedFolder}
                    style={{ width: 200 }}
                    allowClear
                    options={flattenFolders(folders).map((f) => ({ label: f.name, value: f.id }))}
                  />
                  <span style={{ color: 'var(--ice-text-muted)', fontSize: 12, marginLeft: 8 }}>
                    共 {filteredDocs.length} 个文档
                  </span>
                </div>
                <div className="doc-toolbar-right">
                  <div className="kb-search-box" style={{ maxWidth: 240 }}>
                    <SearchOutlined className="kb-search-icon" />
                    <input
                      type="text"
                      placeholder="搜索文件名..."
                      style={{ fontSize: 12, padding: '7px 12px 7px 34px' }}
                    />
                  </div>
                </div>
              </div>

              {/* Document Table */}
              <div className="doc-table">
                <div className="doc-table-header">
                  <div></div>
                  <div>文件名</div>
                  <div>类型</div>
                  <div>大小</div>
                  <div>处理流水线</div>
                  <div>上传时间</div>
                  <div style={{ textAlign: 'right' }}>操作</div>
                </div>
                {filteredDocs.length === 0 ? (
                  <div style={{ padding: 48, textAlign: 'center', color: 'var(--ice-text-muted)' }}>
                    <FileTextOutlined style={{ fontSize: 36, opacity: 0.3 }} />
                    <p style={{ marginTop: 8, fontSize: 13 }}>暂无文档，点击上方"上传文件"添加</p>
                  </div>
                ) : (
                  filteredDocs.map((doc) => {
                    const ft = getFileTypeIcon(doc.file_type)
                    const steps = getPipelineSteps(doc.status)
                    return (
                      <div key={doc.id} className="doc-row">
                        <div className="doc-checkbox" />
                        <div className="doc-name">
                          <div className={`file-type-icon ${ft.cls}`}>{ft.label}</div>
                          <span className="doc-name-text">{doc.original_filename}</span>
                        </div>
                        <div className="doc-type">{doc.file_type}</div>
                        <div className="doc-size">{formatSize(doc.file_size)}</div>
                        <div className="doc-pipeline">
                          {steps.map((s, i) => (
                            <div
                              key={i}
                              className={`pipeline-step ${s}`}
                              title={['提取', '清洗', '分块', '向量化', '存储'][i]}
                            >
                              {s === 'done' ? '\u2713' : s === 'failed' ? '!' : s === 'active' ? i + 1 : i + 1}
                            </div>
                          ))}
                        </div>
                        <div className="doc-date">{formatDate(doc.created_at)}</div>
                        <div className="doc-actions">
                          {doc.status === 'failed' && (
                            <button className="kb-btn-icon" title="重试" style={{ color: 'var(--ice-warning)' }}>
                              <ReloadOutlined />
                            </button>
                          )}
                          {doc.status === 'ready' && (
                            <button className="kb-btn-icon" title="预览">
                              <EyeOutlined />
                            </button>
                          )}
                          <button
                            className="kb-btn-icon"
                            title="删除"
                            style={{ color: 'var(--ice-danger)' }}
                            onClick={() => handleDeleteDoc(doc.id)}
                          >
                            <DeleteOutlined />
                          </button>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>

              {/* Upload Zone */}
              <div
                className="upload-zone"
                style={{ marginTop: 16 }}
                onClick={() => setUploadModal(true)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  setUploadedFiles(Array.from(e.dataTransfer.files))
                  setUploadModal(true)
                }}
              >
                <div className="upload-zone-icon">
                  <UploadOutlined />
                </div>
                <h3>拖拽文件到此处或点击选择</h3>
                <p>支持批量上传，单文件最大 50MB</p>
                <div className="file-types">
                  <span className="kb-tag kb-tag-red">PDF</span>
                  <span className="kb-tag kb-tag-blue">DOCX</span>
                  <span className="kb-tag kb-tag-cyan">MD</span>
                  <span className="kb-tag kb-tag-gray">TXT</span>
                  <span className="kb-tag kb-tag-purple">Code</span>
                  <span className="kb-tag kb-tag-amber">CSV</span>
                  <span className="kb-tag kb-tag-green">JSON</span>
                </div>
              </div>
            </div>
          )}

          {/* ===== Retrieval Test Tab ===== */}
          {activeTab === 'search' && (
            <div className="retrieval-container">
              <div className="retrieval-main">
                <div className="retrieval-input-area">
                  <input
                    type="text"
                    className="retrieval-input"
                    placeholder="输入检索问题，测试知识库检索效果..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  />
                  <Button type="primary" icon={<SearchOutlined />} loading={searchLoading} onClick={handleSearch}>
                    检索
                  </Button>
                </div>

                {searchResults.length > 0 && (
                  <>
                    <div className="retrieval-results-header">
                      <h4>检索结果</h4>
                      <div className="retrieval-meta">
                        <span>{searchResults.length} 条结果</span>
                        {searchMeta && <span>·</span>}
                        {searchMeta && <span>耗时 {searchMeta.time}ms</span>}
                        {searchMeta && <span>·</span>}
                        {searchMeta && <span>Tokens: ~{searchMeta.tokens}</span>}
                      </div>
                    </div>

                    {searchResults.map((r, i) => {
                      const scorePct = Math.round(r.score * 100)
                      const scoreCls = scorePct >= 75 ? 'score-high' : scorePct >= 50 ? 'score-mid' : 'score-low'
                      const ft = getFileTypeIcon(r.document_name.split('.').pop() || '')
                      return (
                        <div key={i} className="retrieval-result">
                          <div className="result-header">
                            <div className="result-source">
                              <div className={`file-type-icon ${ft.cls}`} style={{ width: 24, height: 24, fontSize: 9 }}>
                                {ft.label}
                              </div>
                              <span style={{ fontSize: 13, color: 'var(--ice-text-primary)' }}>{r.document_name}</span>
                              <span className={`kb-tag ${r.score > 0.7 ? 'kb-tag-cyan' : 'kb-tag-purple'}`} style={{ fontSize: 10 }}>
                                {r.score > 0.7 ? '向量+关键词' : '仅向量'}
                              </span>
                            </div>
                            <div className="result-score-bar">
                              <div className="score-track">
                                <div className={`score-fill ${scoreCls}`} style={{ width: `${scorePct}%` }} />
                              </div>
                              <span style={{ fontSize: 12, fontWeight: 600, color: `var(--ice-${scorePct >= 75 ? 'success' : scorePct >= 50 ? 'warning' : 'danger'})` }}>
                                {scorePct}%
                              </span>
                            </div>
                          </div>
                          <div className="result-content">{r.content}</div>
                          <div className="result-footer">
                            <span style={{ fontSize: 11, color: 'var(--ice-text-muted)' }}>
                              Chunk #{r.chunk_index} · {r.folder_path || '根目录'}
                              {r.page_number ? ` · 第 ${r.page_number} 页` : ''}
                            </span>
                            <div className="result-feedback">
                              <button
                                className={`feedback-btn ${feedback[i] === 'up' ? 'active-up' : ''}`}
                                onClick={() => setFeedback((p) => ({ ...p, [i]: 'up' }))}
                              >
                                👍
                              </button>
                              <button
                                className={`feedback-btn ${feedback[i] === 'down' ? 'active-down' : ''}`}
                                onClick={() => setFeedback((p) => ({ ...p, [i]: 'down' }))}
                              >
                                👎
                              </button>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </>
                )}

                {searchResults.length === 0 && searchQuery && !searchLoading && (
                  <div style={{ textAlign: 'center', padding: 48, color: 'var(--ice-text-muted)' }}>
                    <SearchOutlined style={{ fontSize: 36, opacity: 0.3 }} />
                    <p style={{ marginTop: 8, fontSize: 13 }}>暂无检索结果，请尝试其他关键词</p>
                  </div>
                )}
              </div>

              {/* Config Panel */}
              <div className="retrieval-config">
                <div className="config-section">
                  <div className="config-label">检索模式</div>
                  <Select
                    style={{ width: '100%' }}
                    defaultValue="hybrid"
                    options={[
                      { label: '混合检索 (推荐)', value: 'hybrid' },
                      { label: '仅向量检索', value: 'vector' },
                      { label: '仅关键词检索', value: 'keyword' },
                    ]}
                  />
                </div>
                <div className="config-section">
                  <div className="config-label">返回数量 (Top-K)</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <input
                      type="range"
                      min={1}
                      max={20}
                      value={searchParams.topK}
                      onChange={(e) => setSearchParams((p) => ({ ...p, topK: Number(e.target.value) }))}
                      style={{ flex: 1, accentColor: 'var(--ice-primary)' }}
                    />
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-primary)', minWidth: 30, textAlign: 'right' }}>
                      {searchParams.topK}
                    </span>
                  </div>
                </div>
                <div className="config-section">
                  <div className="config-label">重排序</div>
                  <div className="config-row">
                    <span className="label">启用 Cross-Encoder</span>
                    <Toggle on={searchParams.rerank} onClick={() => setSearchParams((p) => ({ ...p, rerank: !p.rerank }))} />
                  </div>
                  <div className="config-row">
                    <span className="label">模型</span>
                    <span className="value" style={{ fontSize: 11 }}>bge-reranker</span>
                  </div>
                </div>
                {searchMeta && (
                  <div className="config-section">
                    <div className="config-label">检索统计</div>
                    <div className="config-row">
                      <span className="label">检索耗时</span>
                      <span className="value">{searchMeta.time}ms</span>
                    </div>
                    <div className="config-row">
                      <span className="label">Token 消耗</span>
                      <span className="value">~{searchMeta.tokens}</span>
                    </div>
                    <div className="config-row">
                      <span className="label">返回结果</span>
                      <span className="value">{searchResults.length} 条</span>
                    </div>
                  </div>
                )}
                <div className="config-section">
                  <div className="config-label">质量反馈</div>
                  <div className="config-row">
                    <span className="label">👍 有用</span>
                    <span className="value" style={{ color: 'var(--ice-success)' }}>
                      {Object.values(feedback).filter((v) => v === 'up').length}
                    </span>
                  </div>
                  <div className="config-row">
                    <span className="label">👎 没用</span>
                    <span className="value" style={{ color: 'var(--ice-danger)' }}>
                      {Object.values(feedback).filter((v) => v === 'down').length}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ===== Statistics Tab ===== */}
          {activeTab === 'stats' && (
            <div>
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-card-icon" style={{ background: 'var(--ice-primary-10)', color: 'var(--ice-primary)' }}>
                    <FileTextOutlined />
                  </div>
                  <div className="stat-card-value">{stats.total}</div>
                  <div className="stat-card-label">文档总数</div>
                </div>
                <div className="stat-card">
                  <div className="stat-card-icon" style={{ background: 'var(--ice-secondary-10)', color: '#a78bfa' }}>
                    <BarChartOutlined />
                  </div>
                  <div className="stat-card-value">{stats.ready}</div>
                  <div className="stat-card-label">已完成处理</div>
                </div>
                <div className="stat-card">
                  <div className="stat-card-icon" style={{ background: 'rgba(245,158,11,.12)', color: 'var(--ice-warning)' }}>
                    <ReloadOutlined />
                  </div>
                  <div className="stat-card-value">{stats.processing + stats.pending}</div>
                  <div className="stat-card-label">处理中/等待</div>
                </div>
                <div className="stat-card">
                  <div className="stat-card-icon" style={{ background: 'var(--ice-danger-soft)', color: 'var(--ice-danger)' }}>
                    <DeleteOutlined />
                  </div>
                  <div className="stat-card-value">{stats.failed}</div>
                  <div className="stat-card-label">处理失败</div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div className="chart-card">
                  <h4>文档处理状态分布</h4>
                  <div style={{ display: 'flex', gap: 24, alignItems: 'center', padding: '16px 0' }}>
                    <div style={{ position: 'relative', width: 120, height: 120 }}>
                      <div
                        style={{
                          width: 120,
                          height: 120,
                          borderRadius: '50%',
                          background: stats.total > 0
                            ? `conic-gradient(var(--ice-success) 0% ${(stats.ready / stats.total) * 100}%, var(--ice-warning) ${(stats.ready / stats.total) * 100}% ${((stats.ready + stats.processing) / stats.total) * 100}%, var(--ice-danger) ${((stats.ready + stats.processing) / stats.total) * 100}% ${((stats.ready + stats.processing + stats.failed) / stats.total) * 100}%, var(--ice-text-muted) ${((stats.ready + stats.processing + stats.failed) / stats.total) * 100}% 100%)`
                            : 'var(--ice-bg-secondary)',
                        }}
                      />
                      <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', textAlign: 'center' }}>
                        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--ice-text-primary)' }}>{stats.total}</div>
                        <div style={{ fontSize: 11, color: 'var(--ice-text-muted)' }}>总计</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="kb-status-dot success" />
                        <span style={{ fontSize: 13, color: 'var(--ice-text-secondary)' }}>已完成</span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-text-primary)' }}>{stats.ready}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="kb-status-dot processing" />
                        <span style={{ fontSize: 13, color: 'var(--ice-text-secondary)' }}>处理中</span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-text-primary)' }}>{stats.processing}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="kb-status-dot error" />
                        <span style={{ fontSize: 13, color: 'var(--ice-text-secondary)' }}>失败</span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-text-primary)' }}>{stats.failed}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="kb-status-dot idle" />
                        <span style={{ fontSize: 13, color: 'var(--ice-text-secondary)' }}>等待中</span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-text-primary)' }}>{stats.pending}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="chart-card">
                  <h4>文件夹分布</h4>
                  <div className="hot-queries" style={{ marginTop: 8 }}>
                    {folders.length === 0 ? (
                      <div style={{ color: 'var(--ice-text-muted)', fontSize: 13, textAlign: 'center', padding: 24 }}>
                        暂无文件夹数据
                      </div>
                    ) : (
                      folders.slice(0, 7).map((f, i) => (
                        <div key={f.id} className="hot-query-item">
                          <div className={`hot-query-rank ${i < 3 ? 'top' : ''}`}>{i + 1}</div>
                          <span className="hot-query-text">{f.name}</span>
                          <span className="hot-query-count">{f.document_count} 文档</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ===== RAG Config Tab ===== */}
          {activeTab === 'config' && (
            <div>
              <div className="chart-card">
                <h4>RAG 检索流水线</h4>
                <div className="pipeline-viz">
                  <div className="pipeline-node">
                    <div className="pipeline-node-icon"><SearchOutlined /></div>
                    <span className="pipeline-node-label">混合检索</span>
                  </div>
                  <span className="pipeline-arrow">→</span>
                  <div className="pipeline-node">
                    <div className="pipeline-node-icon"><BarChartOutlined /></div>
                    <span className="pipeline-node-label">RRF 融合</span>
                  </div>
                  <span className="pipeline-arrow">→</span>
                  <div className="pipeline-node">
                    <div className="pipeline-node-icon"><SettingOutlined /></div>
                    <span className="pipeline-node-label">MMR 去重</span>
                  </div>
                  <span className="pipeline-arrow">→</span>
                  <div className="pipeline-node">
                    <div className="pipeline-node-icon"><ReloadOutlined /></div>
                    <span className="pipeline-node-label">Cross-Encoder 重排</span>
                  </div>
                  <span className="pipeline-arrow">→</span>
                  <div className="pipeline-node">
                    <div className="pipeline-node-icon"><FileTextOutlined /></div>
                    <span className="pipeline-node-label">上下文组装</span>
                  </div>
                </div>
              </div>

              <div className="rag-config-grid">
                {/* Retrieval Config */}
                <div className="config-card">
                  <h4><SearchOutlined style={{ color: 'var(--ice-primary)' }} /> 检索配置</h4>
                  <div className="config-desc">控制检索策略和返回结果数量</div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">混合检索</div>
                      <div className="config-item-hint">向量检索 + 关键词检索 + RRF 融合</div>
                    </div>
                    <Toggle on={ragConfig.hybridSearch} onClick={() => setRagConfig((p) => ({ ...p, hybridSearch: !p.hybridSearch }))} />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">查询改写</div>
                      <div className="config-item-hint">使用 LLM 智能改写用户查询</div>
                    </div>
                    <Toggle on={ragConfig.queryRewrite} onClick={() => setRagConfig((p) => ({ ...p, queryRewrite: !p.queryRewrite }))} />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">Top-K 初筛数量</div>
                      <div className="config-item-hint">检索阶段返回的候选数量</div>
                    </div>
                    <InputNumber
                      value={ragConfig.topK}
                      onChange={(v) => setRagConfig((p) => ({ ...p, topK: v || 20 }))}
                      style={{ width: 100 }}
                    />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">最低相关度阈值</div>
                      <div className="config-item-hint">低于此分数的结果将被过滤</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: 200 }}>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={ragConfig.minScore}
                        onChange={(e) => setRagConfig((p) => ({ ...p, minScore: Number(e.target.value) }))}
                        style={{ flex: 1, accentColor: 'var(--ice-primary)' }}
                      />
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-primary)', minWidth: 40, textAlign: 'right' }}>
                        {ragConfig.minScore.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Rerank Config */}
                <div className="config-card">
                  <h4><BarChartOutlined style={{ color: 'var(--ice-secondary)' }} /> 重排序配置</h4>
                  <div className="config-desc">Cross-Encoder 精排，提升结果相关性</div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">启用重排序</div>
                      <div className="config-item-hint">使用 Cross-Encoder 精排候选结果</div>
                    </div>
                    <Toggle on={ragConfig.rerankEnabled} onClick={() => setRagConfig((p) => ({ ...p, rerankEnabled: !p.rerankEnabled }))} />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">重排模型</div>
                      <div className="config-item-hint">Cross-Encoder 模型选择</div>
                    </div>
                    <Select
                      style={{ width: 180 }}
                      value={ragConfig.rerankModel}
                      onChange={(v) => setRagConfig((p) => ({ ...p, rerankModel: v }))}
                      options={[
                        { label: 'bge-reranker-base', value: 'bge-reranker-base' },
                        { label: 'bge-reranker-large', value: 'bge-reranker-large' },
                        { label: 'cohere-rerank', value: 'cohere-rerank' },
                      ]}
                    />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">重排保留数量</div>
                      <div className="config-item-hint">重排后保留的最终结果数</div>
                    </div>
                    <InputNumber
                      value={ragConfig.rerankTopN}
                      onChange={(v) => setRagConfig((p) => ({ ...p, rerankTopN: v || 10 }))}
                      style={{ width: 100 }}
                    />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">MMR 去重</div>
                      <div className="config-item-hint">消除重复/高度相似的内容片段</div>
                    </div>
                    <Toggle on={ragConfig.mmrEnabled} onClick={() => setRagConfig((p) => ({ ...p, mmrEnabled: !p.mmrEnabled }))} />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">MMR 相似度阈值</div>
                      <div className="config-item-hint">高于此阈值的内容将被去重</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: 200 }}>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={ragConfig.mmrThreshold}
                        onChange={(e) => setRagConfig((p) => ({ ...p, mmrThreshold: Number(e.target.value) }))}
                        style={{ flex: 1, accentColor: 'var(--ice-primary)' }}
                      />
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-primary)', minWidth: 40, textAlign: 'right' }}>
                        {ragConfig.mmrThreshold.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Context Config */}
                <div className="config-card">
                  <h4><FileTextOutlined style={{ color: 'var(--ice-accent)' }} /> 上下文配置</h4>
                  <div className="config-desc">控制注入 LLM 的上下文内容</div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">最大上下文 Tokens</div>
                      <div className="config-item-hint">注入 LLM 的检索内容上限</div>
                    </div>
                    <InputNumber
                      value={ragConfig.maxContextTokens}
                      onChange={(v) => setRagConfig((p) => ({ ...p, maxContextTokens: v || 4000 }))}
                      style={{ width: 100 }}
                    />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">标注来源</div>
                      <div className="config-item-hint">在回答中标注检索来源文件</div>
                    </div>
                    <Toggle on={ragConfig.citeSource} onClick={() => setRagConfig((p) => ({ ...p, citeSource: !p.citeSource }))} />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">来源格式</div>
                      <div className="config-item-hint">来源标注的显示格式</div>
                    </div>
                    <Select
                      style={{ width: 180 }}
                      value={ragConfig.sourceFormat}
                      onChange={(v) => setRagConfig((p) => ({ ...p, sourceFormat: v }))}
                      options={[
                        { label: '[来源: 文件名, 相关度: X%]', value: '[来源: 文件名, 相关度: X%]' },
                        { label: '引用编号 [1] [2]', value: '引用编号 [1] [2]' },
                        { label: '脚注样式', value: '脚注样式' },
                      ]}
                    />
                  </div>
                </div>

                {/* Chunk Config */}
                <div className="config-card">
                  <h4><SettingOutlined style={{ color: 'var(--ice-warning)' }} /> 分块配置</h4>
                  <div className="config-desc">文档切分策略参数</div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">分块策略</div>
                      <div className="config-item-hint">文档切分算法</div>
                    </div>
                    <Select
                      style={{ width: 180 }}
                      value={ragConfig.chunkStrategy}
                      onChange={(v) => setRagConfig((p) => ({ ...p, chunkStrategy: v }))}
                      options={Object.entries(CHUNKING_LABELS).map(([v, l]) => ({ label: l, value: v }))}
                    />
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">分块大小 (tokens)</div>
                      <div className="config-item-hint">每个分块的最大 token 数</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: 200 }}>
                      <input
                        type="range"
                        min={100}
                        max={4000}
                        step={50}
                        value={ragConfig.chunkSize}
                        onChange={(e) => setRagConfig((p) => ({ ...p, chunkSize: Number(e.target.value) }))}
                        style={{ flex: 1, accentColor: 'var(--ice-primary)' }}
                      />
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-primary)', minWidth: 50, textAlign: 'right' }}>
                        {ragConfig.chunkSize}
                      </span>
                    </div>
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">重叠大小 (tokens)</div>
                      <div className="config-item-hint">相邻分块的重叠 token 数</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: 200 }}>
                      <input
                        type="range"
                        min={0}
                        max={500}
                        step={10}
                        value={ragConfig.chunkOverlap}
                        onChange={(e) => setRagConfig((p) => ({ ...p, chunkOverlap: Number(e.target.value) }))}
                        style={{ flex: 1, accentColor: 'var(--ice-primary)' }}
                      />
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ice-primary)', minWidth: 50, textAlign: 'right' }}>
                        {ragConfig.chunkOverlap}
                      </span>
                    </div>
                  </div>
                  <div className="config-item">
                    <div className="config-item-left">
                      <div className="config-item-name">最小分块大小</div>
                      <div className="config-item-hint">小于此值的分块将被丢弃</div>
                    </div>
                    <InputNumber
                      value={ragConfig.minChunkSize}
                      onChange={(v) => setRagConfig((p) => ({ ...p, minChunkSize: v || 50 }))}
                      style={{ width: 100 }}
                    />
                  </div>
                </div>
              </div>

              <div className="save-bar">
                <Button onClick={() => {
                  setRagConfig({
                    hybridSearch: true, queryRewrite: true, topK: 20, minScore: 0.3,
                    rerankEnabled: true, rerankModel: 'bge-reranker-base', rerankTopN: 10,
                    mmrEnabled: true, mmrThreshold: 0.5,
                    maxContextTokens: 4000, citeSource: true, sourceFormat: '[来源: 文件名, 相关度: X%]',
                    chunkStrategy: 'recursive_character', chunkSize: 500, chunkOverlap: 50, minChunkSize: 50,
                  })
                  message.info('已恢复默认配置')
                }}>
                  恢复默认
                </Button>
                <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveRagConfig}>
                  保存配置
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Folder Modal */}
      <Modal title="新建文件夹" open={folderModal} onCancel={() => setFolderModal(false)} footer={null} width={400}>
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            await fetch('/api/knowledge-bases/' + id + '/folders', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', ...authHeaders() },
              body: JSON.stringify({ name: values.name, parent_id: selectedFolder }),
            })
            setFolderModal(false)
            form.resetFields()
            const res = await fetch('/api/knowledge-bases/' + id + '/folders/tree', { headers: authHeaders() })
            setFolders(await res.json())
            message.success('文件夹已创建')
          }}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="文件夹名称" />
          </Form.Item>
          <Button type="primary" htmlType="submit">创建</Button>
        </Form>
      </Modal>

      {/* Upload Modal */}
      <Modal title="上传文件" open={uploadModal} onCancel={() => { setUploadModal(false); setUploadedFiles([]) }} footer={null}>
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); setUploadedFiles(Array.from(e.dataTransfer.files)) }}
          onClick={() => document.getElementById('kb-file-input')?.click()}
          style={{ border: '2px dashed var(--ice-border)', borderRadius: 12, padding: 32, textAlign: 'center', cursor: 'pointer', marginBottom: 16 }}
        >
          <UploadOutlined style={{ fontSize: 32, color: 'var(--ice-primary)' }} />
          <p style={{ color: 'var(--ice-text-secondary)', marginTop: 8 }}>拖拽文件到此区域或点击选择</p>
          <p style={{ color: 'var(--ice-text-muted)', fontSize: 12 }}>支持 PDF, DOCX, TXT, MD, Code · 最大 50MB</p>
          <input
            id="kb-file-input"
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.md,.csv,.json,.py,.js,.ts,.java,.go,.rs"
            style={{ display: 'none' }}
            onChange={(e) => e.target.files && setUploadedFiles(Array.from(e.target.files))}
          />
        </div>
        {uploadedFiles.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            {uploadedFiles.map((f, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--ice-border)' }}>
                <span style={{ color: 'var(--ice-text-primary)', fontSize: 13 }}>{f.name}</span>
                <span style={{ color: 'var(--ice-text-secondary)', fontSize: 12 }}>{formatSize(f.size)}</span>
              </div>
            ))}
          </div>
        )}
        <Button type="primary" loading={uploading} onClick={handleUpload} disabled={!uploadedFiles.length}>
          开始上传
        </Button>
      </Modal>
    </div>
  )
}
