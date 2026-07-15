import { Modal, Input, Button, Image } from 'antd'
import { useEffect, useState } from 'react'
import type { GalleryRecord } from '@/services/gallery'

interface RedoModalProps {
  open: boolean
  record: GalleryRecord | null
  taskId: number | null
  prompt: string
  loading: boolean
  onClose: () => void
  onPromptChange: (prompt: string) => void
  onSubmit: () => void
}

export default function RedoModal({
  open,
  record,
  taskId,
  prompt,
  loading,
  onClose,
  onPromptChange,
  onSubmit,
}: RedoModalProps) {
  const [localPrompt, setLocalPrompt] = useState(prompt)

  useEffect(() => {
    if (open) setLocalPrompt(prompt)
  }, [open, prompt])

  if (!record || !taskId) return null

  const realImage = record.result_url && !record.result_url.endsWith('.svg')
    ? record.result_url
    : null

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={560}
      className="g-modal redo-modal"
      title="重新生成"
      destroyOnClose
    >
      <div className="redo-modal-body">
        <div className="redo-header">
          {realImage ? (
            <div className="redo-thumb">
              <Image src={realImage} alt={record.title || ''} preview={false} />
            </div>
          ) : (
            <div className="redo-thumb redo-thumb-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M3 15l5-5 4 4 3-3 6 6" />
              </svg>
            </div>
          )}
          <div className="redo-meta">
            <h4>{record.title || '未命名图片'}</h4>
            <p>编辑中文提示词，重新生成此图</p>
          </div>
        </div>

        <div className="redo-field">
          <label htmlFor="redo-prompt">中文提示词</label>
          <Input.TextArea
            id="redo-prompt"
            rows={6}
            value={localPrompt}
            onChange={(e) => setLocalPrompt(e.target.value)}
            placeholder="输入中文提示词，AI 将按此重新生成"
            maxLength={2000}
            showCount
          />
          <p className="redo-hint">修改后点击「重新生成」，后台将按当前提示词出图。</p>
        </div>

        <div className="redo-actions">
          <Button onClick={onClose} disabled={loading}>取消</Button>
          <Button
            type="primary"
            loading={loading}
            disabled={!localPrompt.trim()}
            onClick={() => {
              onPromptChange(localPrompt)
              onSubmit()
            }}
          >
            重新生成
          </Button>
        </div>
      </div>
    </Modal>
  )
}
