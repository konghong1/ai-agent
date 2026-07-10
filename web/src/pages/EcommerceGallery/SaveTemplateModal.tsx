import { useEffect, useState } from 'react'
import { Modal, Input, Image, Empty } from 'antd'

interface Props {
  open: boolean
  onClose: () => void
  defaultName?: string
  defaultCoverUrl?: string | null
  projectImages: { id: number; url: string; original?: boolean }[]
  onSave: (payload: { name: string; coverUrl: string | null }) => Promise<void>
}

export default function SaveTemplateModal({
  open, onClose, defaultName = '', defaultCoverUrl = null, projectImages, onSave,
}: Props) {
  const [name, setName] = useState(defaultName)
  const [coverUrl, setCoverUrl] = useState<string | null>(defaultCoverUrl || null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName(defaultName)
      setCoverUrl(defaultCoverUrl || null)
    }
  }, [open, defaultName, defaultCoverUrl])

  const handleOk = async () => {
    const trimmed = name.trim()
    if (!trimmed) return
    setSaving(true)
    try {
      await onSave({ name: trimmed, coverUrl: coverUrl || null })
      setName('')
      setCoverUrl(null)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title="另存为模板"
      destroyOnClose
      width={520}
      confirmLoading={saving}
      onOk={handleOk}
      okText="保存模板"
      cancelText="取消"
    >
      <div className="stm-body">
        <div className="stm-field">
          <label className="stm-label">模板名称</label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            showCount
            placeholder="请输入模板名称"
          />
        </div>

        <div className="stm-field">
          <label className="stm-label">
            模板封面
            <span className="stm-tip">（可选，默认使用当前产品图片 / 类型图片）</span>
          </label>
          {projectImages.length === 0 ? (
            <Empty description="请先在左侧上传产品图" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <div className="stm-cover-grid">
              {projectImages.map((img) => (
                <div
                  key={img.id}
                  className={`stm-cover-thumb ${coverUrl === img.url ? 'selected' : ''}`}
                  onClick={() => setCoverUrl(coverUrl === img.url ? null : img.url)}
                  title="设为模板封面"
                >
                  <Image src={img.url} alt="" preview={false} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
