import { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, Modal, message, Switch } from 'antd'
import {
  PlusOutlined, BookOutlined, DeleteOutlined, EditOutlined,
  SearchOutlined, AppstoreOutlined, UnorderedListOutlined,
} from '@ant-design/icons'
import { authHeaders } from '@/services/auth'
import './kb-styles.css'

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

/** Pick a stable icon color based on KB id */
const iconColors = [
  { bg: 'var(--ice-primary-10)', color: 'var(--ice-primary)' },
  { bg: 'var(--ice-secondary-10)', color: '#a78bfa' },
  { bg: 'var(--ice-accent-10)', color: 'var(--ice-accent)' },
  { bg: 'rgba(245,158,11,.12)', color: 'var(--ice-warning)' },
  { bg: 'rgba(136,153,170,.12)', color: 'var(--ice-text-secondary)' },
]
const getColor = (id: number) => iconColors[id % iconColors.length]

function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const min = Math.floor(diff / 60000)
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day} 天前`
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

export default function KnowledgeBaseList() {
  const navigate = useNavigate()
  const [kbs, setKbs] = useState<KB[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<KB | null>(null)
  const [searchText, setSearchText] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [form] = Form.useForm()

  const fetchKbs = async () => {
    try {
      const res = await fetch('/api/knowledge-bases', { headers: authHeaders() })
      setKbs(res.ok ? await res.json() : [])
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchKbs() }, [])

  const filteredKbs = useMemo(() => {
    if (!searchText.trim()) return kbs
    const q = searchText.toLowerCase()
    return kbs.filter(kb =>
      kb.name.toLowerCase().includes(q) ||
      (kb.description || '').toLowerCase().includes(q)
    )
  }, [kbs, searchText])

  const handleSave = async (values: any) => {
    setLoading(true)
    try {
      const url = editing ? `/api/knowledge-bases/${editing.id}` : '/api/knowledge-bases'
      const method = editing ? 'PATCH' : 'POST'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(values),
      })
      if (!res.ok) throw new Error('保存失败')
      message.success(editing ? '更新成功' : '创建成功')
      setModalOpen(false)
      setEditing(null)
      form.resetFields()
      fetchKbs()
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    Modal.confirm({
      title: '确认删除',
      content: '删除知识库会同时删除所有文档和向量数据，此操作不可撤销。',
      okText: '删除',
      okType: 'danger',
      onOk: async () => {
        const res = await fetch(`/api/knowledge-bases/${id}`, {
          method: 'DELETE',
          headers: authHeaders(),
        })
        if (res.ok) {
          message.success('已删除')
          fetchKbs()
        }
      },
    })
  }

  const handleEdit = (kb: KB, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditing(kb)
    form.setFieldsValue(kb)
    setModalOpen(true)
  }

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    setModalOpen(true)
  }

  return (
    <div className="kb-list-page">
      {/* Header */}
      <div className="kb-list-header">
        <div>
          <h1>知识库</h1>
          <div className="subtitle">管理知识库、文档和 RAG 检索配置</div>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建知识库
        </Button>
      </div>

      {/* Toolbar */}
      <div className="kb-toolbar">
        <div className="kb-search-box">
          <SearchOutlined className="kb-search-icon" />
          <input
            type="text"
            placeholder="搜索知识库名称..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </div>
        <div className="kb-view-toggle">
          <button
            className={viewMode === 'grid' ? 'active' : ''}
            onClick={() => setViewMode('grid')}
            title="网格视图"
          >
            <AppstoreOutlined />
          </button>
          <button
            className={viewMode === 'list' ? 'active' : ''}
            onClick={() => setViewMode('list')}
            title="列表视图"
          >
            <UnorderedListOutlined />
          </button>
        </div>
      </div>

      {/* KB Grid */}
      {filteredKbs.length === 0 && !searchText ? (
        <div style={{ textAlign: 'center', padding: 64, color: 'var(--ice-text-muted)' }}>
          <BookOutlined style={{ fontSize: 48, opacity: 0.3 }} />
          <p style={{ marginTop: 12, fontSize: 14 }}>暂无知识库，点击"新建知识库"开始</p>
        </div>
      ) : (
        <div className="kb-grid" style={viewMode === 'list' ? { gridTemplateColumns: '1fr' } : undefined}>
          {filteredKbs.map((kb) => {
            const ic = getColor(kb.id)
            return (
              <div
                key={kb.id}
                className="kb-card"
                onClick={() => navigate(`/knowledge-bases/${kb.id}`)}
                style={viewMode === 'list' ? { display: 'flex', alignItems: 'center', gap: 16, minHeight: 'auto' } : undefined}
              >
                <div className="kb-card-header" style={viewMode === 'list' ? { marginBottom: 0, flex: 1, minWidth: 0 } : undefined}>
                  <div className="kb-card-icon" style={{ background: ic.bg, color: ic.color }}>
                    <BookOutlined />
                  </div>
                  {viewMode === 'grid' && (
                    <div className="kb-card-actions">
                      <button className="kb-btn-icon" onClick={(e) => handleEdit(kb, e)} title="编辑">
                        <EditOutlined />
                      </button>
                      <button
                        className="kb-btn-icon"
                        onClick={(e) => handleDelete(kb.id, e)}
                        title="删除"
                        style={{ color: 'var(--ice-danger)' }}
                      >
                        <DeleteOutlined />
                      </button>
                    </div>
                  )}
                </div>
                <div style={viewMode === 'list' ? { flex: 2, minWidth: 0 } : undefined}>
                  <div className="kb-card-title">{kb.name}</div>
                  <div className="kb-card-desc">{kb.description || '暂无描述'}</div>
                  {viewMode === 'grid' && (
                    <>
                      <div className="kb-card-stats">
                        <div className="kb-stat">
                          <div className="kb-stat-value">{kb.chunk_size}</div>
                          <div className="kb-stat-label">分块大小</div>
                        </div>
                        <div className="kb-stat">
                          <div className="kb-stat-value">{kb.chunk_overlap}</div>
                          <div className="kb-stat-label">重叠</div>
                        </div>
                        <div className="kb-stat">
                          <div className="kb-stat-value">{kb.enabled ? 'ON' : 'OFF'}</div>
                          <div className="kb-stat-label">状态</div>
                        </div>
                      </div>
                      <div className="kb-card-footer">
                        <div className="kb-card-meta">
                          <span className={`kb-status-dot ${kb.enabled ? 'success' : 'idle'}`} />
                          <span>{kb.enabled ? '已启用' : '已禁用'} · {formatRelativeTime(kb.updated_at || kb.created_at)}</span>
                        </div>
                        <span className="kb-tag kb-tag-cyan">{kb.embedding_model}</span>
                      </div>
                    </>
                  )}
                  {viewMode === 'list' && (
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 4 }}>
                      <span className="kb-tag kb-tag-cyan">{kb.embedding_model}</span>
                      <span style={{ fontSize: 12, color: 'var(--ice-text-muted)' }}>
                        Chunk: {kb.chunk_size} / Overlap: {kb.chunk_overlap}
                      </span>
                      <span style={{ fontSize: 12, color: 'var(--ice-text-muted)' }}>·</span>
                      <span style={{ fontSize: 12, color: 'var(--ice-text-muted)' }}>
                        {kb.enabled ? '已启用' : '已禁用'} · {formatRelativeTime(kb.updated_at || kb.created_at)}
                      </span>
                      <div style={{ flex: 1 }} />
                      <button className="kb-btn-icon" onClick={(e) => handleEdit(kb, e)} title="编辑">
                        <EditOutlined />
                      </button>
                      <button
                        className="kb-btn-icon"
                        onClick={(e) => handleDelete(kb.id, e)}
                        title="删除"
                        style={{ color: 'var(--ice-danger)' }}
                      >
                        <DeleteOutlined />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}

          {/* Create new KB card */}
          <div className="kb-card kb-card-create" onClick={openCreate}>
            <div className="plus-icon">
              <PlusOutlined />
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ice-text-primary)', marginBottom: 4 }}>
              新建知识库
            </div>
            <div style={{ fontSize: 12, color: 'var(--ice-text-muted)' }}>
              上传文档，构建专属知识检索
            </div>
          </div>
        </div>
      )}

      {/* Create / Edit Modal */}
      <Modal
        title={editing ? '编辑知识库' : '新建知识库'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields() }}
        footer={null}
        width={560}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={{ chunk_size: 500, chunk_overlap: 50, enabled: true }}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如: 产品文档" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="知识库描述" />
          </Form.Item>
          <Form.Item name="embedding_model" label="嵌入模型">
            <Input placeholder="text-embedding-3-small" />
          </Form.Item>
          <Form.Item name="chunk_size" label="分块大小">
            <Input type="number" min={100} max={4000} />
          </Form.Item>
          <Form.Item name="chunk_overlap" label="重叠大小">
            <Input type="number" min={0} max={500} />
          </Form.Item>
          <Form.Item name="enabled" valuePropName="checked" label="启用">
            <Switch />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={loading} style={{ marginRight: 8 }}>
              确定
            </Button>
            <Button onClick={() => { setModalOpen(false); setEditing(null); form.resetFields() }}>
              取消
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
