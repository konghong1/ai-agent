import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeftOutlined, PlusOutlined, UploadOutlined, SearchOutlined, DeleteOutlined } from '@ant-design/icons'
import { Typography, Form, Input, Button, Space, Table, Modal, Select, Tag, message } from 'antd'
import { IceCrystalCard } from '@/components/IceCrystalCard'

import { authHeaders, authHeadersRaw } from '@/services/auth'

const { Text, Title } = Typography

interface KBFolder { id: number; name: string; parent_id: number | null; children: KBFolder[]; document_count: number }
interface KBDoc { id: number; original_filename: string; file_type: string; file_size: number; status: string; error_message: string | null; created_at: string }

function flattenFolders(folders: KBFolder[]): KBFolder[] {
  const result: KBFolder[] = []
  const walk = (items: KBFolder[]) => items.forEach(f => { result.push(f); f.children && walk(f.children) })
  walk(folders)
  return result
}

export default function KBDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [kb, setKb] = useState<any>(null)
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
    { title: '文件名', dataIndex: 'original_filename', key: 'name',
      render: (name: string, record: KBDoc) => (
        <Space><span style={{ color: '#e8f4f8' }}>{name}</span><Tag>{record.file_type}</Tag></Space>
      )},
    { title: '大小', dataIndex: 'file_size', key: 'size', width: 100, render: (s: number) => `${(s / 1024).toFixed(1)} KB` },
    { title: '状态', dataIndex: 'status', key: 'status', width: 120, render: (s: string) => statusTag(s) },
    { title: '创建时间', dataIndex: 'created_at', key: 'time', width: 180, render: (t: string) => new Date(t).toLocaleString('zh-CN') },
    { title: '操作', key: 'action', width: 80, render: (_: any, r: KBDoc) => (
      <Button type="text" danger icon={<DeleteOutlined />} size="small" onClick={() => handleDeleteDoc(r.id)} />
    )}]

  const renderFolderTree = (items: KBFolder[], depth = 0) =>
    items.map(f => (
      <div key={f.id} style={{ paddingLeft: depth * 20, cursor: 'pointer', padding: '4px 8px', borderRadius: 4 }}
        onClick={() => setActiveFolderId(f.id)}
        onMouseEnter={(e) => { (e.target as HTMLElement).style.background = 'rgba(0,212,255,0.06)' }}
        onMouseLeave={(e) => { (e.target as HTMLElement).style.background = 'transparent' }}>
        <Space>
          <span style={{ color: activeFolderId === f.id ? '#00d4ff' : '#8899aa' }}>📁</span>
          <Text style={{ color: '#e8f4f8', fontWeight: activeFolderId === f.id ? 600 : 400 }}>{f.name}</Text>
          {f.document_count > 0 && <Tag color="blue">{f.document_count}</Tag>}
        </Space>
        {f.children && renderFolderTree(f.children, depth + 1)}
      </div>
    ))

  return (
    <div>
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/knowledge-bases')}
        style={{ color: '#e8f4f8', marginBottom: 16 }}>返回知识库列表</Button>

      {kb && (
        <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ marginBottom: 16 }}>
          <Title level={4} style={{ color: '#e8f4f8', margin: 0 }}>📚 {kb.name}</Title>
          <Text type="secondary">{kb.description}</Text>
        </IceCrystalCard>
      )}

      <Row gutter={16}>
        <Col span={6}>
          <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ minHeight: 300 }}>
            <div style={{ padding: 8 }}>
              <Title level={5} style={{ color: '#e8f4f8', marginBottom: 12 }}>📂 文件夹</Title>
              <Button type="dashed" block icon={<PlusOutlined />} onClick={() => setFolderModal(true)} style={{ marginBottom: 12 }}>新建文件夹</Button>
              {renderFolderTree(folders)}
            </div>
          </IceCrystalCard>
        </Col>

        <Col span={18}>
          <Tabs items={[
            {
              key: 'docs', label: '📄 文档管理',
              children: (
                <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ }}>
                  <Space style={{ marginBottom: 16 }}>
                    <Button icon={<UploadOutlined />} onClick={() => setUploadModal(true)}>上传文件</Button>
                    <Select placeholder="选择文件夹" value={selectedFolder || undefined} onChange={setSelectedFolder} style={{ width: 200 }}
                      options={flattenFolders(folders).map(f => ({ label: f.name, value: f.id }))} />
                  </Space>
                  <Table columns={docColumns} dataSource={documents} rowKey="id" pagination={{ pageSize: 10 }} scroll={{ x: 800 }} />
                </IceCrystalCard>
              )},
            {
              key: 'search', label: '🔍 检索测试',
              children: (
                <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ }}>
                  <Space.Compact style={{ marginBottom: 16 }}>
                    <Input placeholder="输入检索问题..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                      onPressEnter={handleSearch} style={{ flex: 1 }} />
                    <Button type="primary" icon={<SearchOutlined />} loading={searchLoading} onClick={handleSearch}>检索</Button>
                  </Space.Compact>
                  {searchResults.map((r: any, i: number) => (
                    <div key={i} style={{ padding: 12, marginBottom: 8, background: 'rgba(0, 212, 255, 0.04)', borderRadius: 8, border: '1px solid rgba(0, 212, 255, 0.08)' }}>
                      <Space style={{ marginBottom: 4 }}>
                        <Tag color="cyan">{r.document_name}</Tag>
                        <Tag color="green">相关度: {(r.score * 100).toFixed(0)}%</Tag>
                      </Space>
                      <Text style={{ color: '#e8f4f8', fontSize: 13 }}>{r.content?.substring(0, 200)}...</Text>
                    </div>
                  ))}
                  {searchResults.length === 0 && searchQuery && <Text type="secondary">暂无检索结果</Text>}
                </IceCrystalCard>
              )}]} />
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
          style={{ border: '2px dashed rgba(0, 212, 255, 0.3)', borderRadius: 12, padding: 32, textAlign: 'center', cursor: 'pointer', marginBottom: 16 }}>
          <UploadOutlined style={{ fontSize: 32, color: '#00d4ff' }} />
          <p style={{ color: '#8899aa', marginTop: 8 }}>拖拽文件到此处 或 点击选择</p>
          <p style={{ color: '#556677', fontSize: 12 }}>支持 PDF, DOCX, TXT, MD, Code · 最大 50MB</p>
          <input type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.json,.py,.js,.ts,.java,.go,.rs"
            style={{ display: 'none' }}
            onChange={(e) => e.target.files && setUploadedFiles(Array.from(e.target.files))}
          />
        </div>
        {uploadedFiles.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            {uploadedFiles.map((f, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <Text style={{ color: '#e8f4f8' }}>{f.name}</Text>
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





