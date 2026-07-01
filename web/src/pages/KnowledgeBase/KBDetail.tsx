import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeftOutlined, PlusOutlined, UploadOutlined, SearchOutlined, DeleteOutlined } from '@ant-design/icons'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Tag, message, Row, Col, Tabs, Badge } from 'antd'
import { IceCrystalCard } from '@/components/IceCrystalCard'
import { useLayoutStore } from '@/stores/layout'
import { authHeaders } from '@/services/auth'

const { Text, Title } = Typography

interface KBFolder { id: number; name: string; parent_id: number | null; children: KBFolder[]; document_count: number }
interface KBDoc { id: number; original_filename: string; file_type: string; file_size: number; status: string; error_message: string | null; created_at: string }

interface KB {
  id: number; name: string; description: string; enabled: boolean
  chunking_strategy: string; chunking_config: Record<string, unknown>; rag_config: Record<string, unknown>
  embedding_model: string; created_at: string
}

const CHUNKING_LABELS: Record<string, string> = {
  recursive_character: '递归字符分块（推荐）',
  fixed_size: '固定大小分块',
  hierarchical: '文档结构分块',
}

function flattenFolders(folders: KBFolder[]): KBFolder[] {
  const result: KBFolder[] = []
  const walk = (items: KBFolder[]) => items.forEach(f => { result.push(f); f.children && walk(f.children) })
  walk(folders)
  return result
}

export default function KBDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const theme = useLayoutStore((s) => s.theme)
  const [kb, setKb] = useState<KB | null>(null)
  const [folders, setFolders] = useState<KBFolder[]>([])
  const [activeFolderId, setActiveFolderId] = useState<number | null>(null)
  const [documents, setDocuments] = useState<KBDoc[]>([])
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [folderModal, setFolderModal] = useState(false)
  const [uploadModal, setUploadModal] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedFolder, setSelectedFolder] = useState<number | null>(null)
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [form] = Form.useForm()

  const themeColorMap: Record<string, string> = {
    techBlue: '#2563EB',
    naturalGreen: '#22C55E',
    elegantPurple: '#7C3AED',
  }
  const primaryColor = themeColorMap[theme] || '#22C55E'

  useEffect(() => {
    Promise.all([
      fetch('/api/knowledge-bases/' + id, { headers: authHeaders() }).then(r => r.json()),
      fetch('/api/knowledge-bases/' + id + '/folders/tree', { headers: authHeaders() }).then(r => r.json()),
      fetch('/api/knowledge-bases/' + id + '/documents', { headers: authHeaders() }).then(r => r.json())]).then(([kbData, folderData, docData]) => {
      setKb(kbData)
      setFolders(folderData)
      setDocuments(docData)
    })
  }, [id])

  const pollStatus = useCallback((docId: number) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/api/knowledge-bases/' + id + '/documents', { headers: authHeaders() })
        const docs = await res.json()
        const doc = docs.find((d: any) => d.id === docId)
        if (doc && ['ready', 'failed'].includes(doc.status)) {
          clearInterval(interval)
          setDocuments(docs)
          message.success(doc.status === 'ready' ? '处理完成' : '处理失败: ' + doc.error_message)
        }
      } catch {}
    }, 2000)
    return () => clearInterval(interval)
  }, [id])

  const handleUpload = async () => {
    if (!uploadedFiles.length) return
    setUploading(true)
    for (const file of uploadedFiles) {
      const fd = new FormData()
      fd.append('file', file)
      if (selectedFolder) fd.append('folder_id', String(selectedFolder))
      try {
        const res = await fetch('/api/knowledge-bases/' + id + '/upload', { method: 'POST', headers: authHeaders(), body: fd })
        const data = await res.json()
        pollStatus(data.document_id)
      } catch (e: any) { message.error(e.message) }
    }
    setUploading(false)
    setUploadModal(false)
    setUploadedFiles([])
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearchLoading(true)
    try {
      const res = await fetch('/api/knowledge-bases/search', {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ kb_id: Number(id), query: searchQuery, top_k: 5 })})
      const data = await res.json()
      setSearchResults(data)
    } catch (e: any) { message.error(e.message) }
    finally { setSearchLoading(false) }
  }

  const handleDeleteDoc = async (docId: number) => {
    await fetch('/api/knowledge-bases/' + id + '/documents/' + docId, { method: 'DELETE', headers: authHeaders() })
    setDocuments(prev => prev.filter(d => d.id !== docId))
    message.success('已删除')
  }

  const statusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      pending: { color: 'default', text: '等待中' },
      processing: { color: 'processing', text: '处理中' },
      ready: { color: 'success', text: '已完成' },
      failed: { color: 'error', text: '失败' }}
    const s = map[status] || map.pending
    return <Badge status={s.color as any} text={s.text} />
  }

  const docColumns = [
    { title: '文件名', dataIndex: 'original_filename', key: 'name', width: 200 },
    { title: '类型', dataIndex: 'file_type', key: 'type', width: 80 },
    { title: '大小', dataIndex: 'file_size', key: 'size', width: 100,
      render: (v: number) => (v / 1024).toFixed(1) + ' KB' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (v: string) => statusTag(v) },
    { title: '错误', dataIndex: 'error_message', key: 'error', ellipsis: true,
      render: (v: string | null) => v || '-' },
    { title: '操作', key: 'action', width: 80, render: (_: any, record: KBDoc) => (
      <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => handleDeleteDoc(record.id)} />
    )},
  ]

  const cc = (kb?.chunking_config as Record<string, unknown>) || {}
  const rc = (kb?.rag_config as Record<string, unknown>) || {}

  return (
    <div>
      <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/knowledge-bases')}
        style={{ color: 'var(--ice-text-secondary)', marginBottom: 16, paddingLeft: 0 }}>
        返回知识库列表
      </Button>

      {kb && (
        <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24, marginBottom: 16 }}>
          <Row gutter={[16, 12]}>
            <Col span={6}><Title level={4} style={{ margin: 0 }}>{kb.name}</Title></Col>
            <Col span={18}><Text type="secondary">{kb.description || '暂无描述'}</Text></Col>
            <Col span={4}><Text type="secondary">切块策略</Text><br/>{CHUNKING_LABELS[kb.chunking_strategy] || kb.chunking_strategy}</Col>
            <Col span={4}><Text type="secondary">分块大小</Text><br/>{(cc.chunk_size_tokens as number) ?? 512} tokens</Col>
            <Col span={4}><Text type="secondary">重叠大小</Text><br/>{(cc.chunk_overlap_tokens as number) ?? 64} tokens</Col>
            <Col span={4}><Text type="secondary">嵌入模型</Text><br/>{kb.embedding_model}</Col>
            <Col span={4}><Text type="secondary">混合检索</Text><br/><Tag color={(rc.hybrid_search as boolean) ? 'green' : 'default'}>{(rc.hybrid_search as boolean) ? '已启用' : '已禁用'}</Tag></Col>
            <Col span={4}><Text type="secondary">重排序</Text><br/><Tag color={(rc.rerank_enabled as boolean) ? 'green' : 'default'}>{(rc.rerank_enabled as boolean) ? '已启用' : '已禁用'}</Tag></Col>
          </Row>
        </IceCrystalCard>
      )}

      <Row gutter={[16, 16]}>
        <Col span={16}>
          <Tabs items={[
            {
              key: 'docs', label: '📁 文档管理',
              children: (
                <IceCrystalCard hoverEffect="none" animation="fadeInUp">
                  <Space style={{ marginBottom: 16 }}>
                    <Button icon={<UploadOutlined />} onClick={() => setUploadModal(true)}>上传文件</Button>
                    <Select placeholder="选择文件夹" value={selectedFolder || undefined} onChange={setSelectedFolder} style={{ width: 200 }}
                      options={flattenFolders(folders).map(f => ({ label: f.name, value: f.id }))} />
                  </Space>
                  <Table columns={docColumns} dataSource={documents} rowKey="id" pagination={{ pageSize: 10 }} scroll={{ x: 800 }} />
                </IceCrystalCard>
              ),
            },
            {
              key: 'search', label: '🔍 检索测试',
              children: (
                <IceCrystalCard hoverEffect="none" animation="fadeInUp">
                  <Space.Compact style={{ marginBottom: 16 }}>
                    <Input placeholder="输入检索问题。" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                      onPressEnter={handleSearch} style={{ flex: 1 }} />
                    <Button type="primary" icon={<SearchOutlined />} loading={searchLoading} onClick={handleSearch}>检索</Button>
                  </Space.Compact>
                  {searchResults.map((r: any, i: number) => (
                    <div key={i} style={{ padding: 12, marginBottom: 8, background: 'var(--ice-bg-hover)', borderRadius: 8, border: '1px solid var(--ice-border)' }}>
                      <Space style={{ marginBottom: 4 }}>
                        <Tag color="cyan">{r.document_name}</Tag>
                        <Tag color="green">相关度 {(r.score * 100).toFixed(0)}%</Tag>
                      </Space>
                      <Text style={{ color: 'var(--ice-text-primary)', fontSize: 13 }}>{r.content?.substring(0, 200)}...</Text>
                    </div>
                  ))}
                  {searchResults.length === 0 && searchQuery && <Text type="secondary">暂无检索结果</Text>}
                </IceCrystalCard>
              ),
            }]} />
        </Col>
      </Row>

      <Modal title="新建文件夹" open={folderModal} onCancel={() => setFolderModal(false)} footer={null} width={400}>
        <Form form={form} layout="vertical" onFinish={async (values) => {
          await fetch('/api/knowledge-bases/' + id + '/folders', {
            method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ name: values.name, parent_id: selectedFolder })})
          setFolderModal(false); form.resetFields()
          const res = await fetch('/api/knowledge-bases/' + id + '/folders/tree', { headers: authHeaders() })
          setFolders(await res.json())
        }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="文件夹名称" />
          </Form.Item>
          <Button type="primary" htmlType="submit">创建</Button>
        </Form>
      </Modal>

      <Modal title="上传文件" open={uploadModal} onCancel={() => setUploadModal(false)} footer={null}>
        <div onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); setUploadedFiles(Array.from(e.dataTransfer.files)) }}
          style={{ border: '2px dashed var(--ice-border)', borderRadius: 12, padding: 32, textAlign: 'center', cursor: 'pointer', marginBottom: 16 }}>
          <UploadOutlined style={{ fontSize: 32, color: primaryColor }} />
          <p style={{ color: 'var(--ice-text-secondary)', marginTop: 8 }}>拖拽文件到此区域或 点击选择</p>
          <p style={{ color: 'var(--ice-text-muted)', fontSize: 12 }}>支持 PDF, DOCX, TXT, MD, Code · 最大 50MB</p>
          <input type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.json,.py,.js,.ts,.java,.go,.rs"
            style={{ display: 'none' }}
            onChange={(e) => e.target.files && setUploadedFiles(Array.from(e.target.files))}
          />
        </div>
        {uploadedFiles.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            {uploadedFiles.map((f, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--ice-border)' }}>
                <Text style={{ color: 'var(--ice-text-primary)' }}>{f.name}</Text>
                <Text type="secondary">{(f.size / 1024).toFixed(1)} KB</Text>
              </div>
            ))}
          </div>
        )}
        <Button type="primary" loading={uploading} onClick={handleUpload} disabled={!uploadedFiles.length}>开始上传</Button>
      </Modal>
    </div>
  )
}
