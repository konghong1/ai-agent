import { useEffect, useState } from 'react'
import { Modal, Input, Select, message, Upload } from 'antd'
import type { UploadProps } from 'antd/es/upload'
import type { GalleryType, GalleryOptions, GalleryPlanItem, GalleryImageModelsResponse, GalleryImage } from '@/services/gallery'
import { aiFill, uploadImages } from '@/services/gallery'

interface Props {
  open: boolean
  onClose: () => void
  projectId: number
  type: GalleryType | null
  item: GalleryPlanItem | undefined
  options: GalleryOptions
  imageModels: GalleryImageModelsResponse
  projectImages: GalleryImage[]
  inheritedModel: { provider_id: number | null; model_name: string | null; model_label: string | null } | null
  marketConfig?: Record<string, string>
  onSave: (payload: {
    type_id: string
    personal_settings: Record<string, string>
    common_settings: Record<string, string>
    output_settings: Record<string, any>
    note: string
    reference_images: string[]
    product_image: string
  }) => void
  onSaveAsTemplate: (payload: {
    type_id: string
    title: string
    personal_settings: Record<string, string>
    common_settings: Record<string, string>
    output_settings: Record<string, any>
    note: string
    reference_images: string[]
    product_image: string
  }) => void
}

const COMMON_KEYS = [
  { key: 'copy_language', label: '文案语种' },
  { key: 'target_market', label: '目标市场' },
  { key: 'ecommerce_platform', label: '电商平台' },
  { key: 'visual_style', label: '视觉风格' },
  { key: 'copy_need', label: '文案需求' },
  { key: 'tone_tendency', label: '色调倾向' },
]
const COMMON_DEFAULTS: Record<string, string> = {
  copy_language: '英语',
  target_market: '北美',
  ecommerce_platform: '亚马逊',
  visual_style: '高级质感风',
  tone_tendency: '高饱和色调',
}

interface SingleTagSelectProps {
  value?: string
  options: { label: string; value: string }[]
  onChange: (val: string) => void
  placeholder?: string
}

function SingleTagSelect({ value, options, onChange, placeholder }: SingleTagSelectProps) {
  const [open, setOpen] = useState(false)
  return (
    <Select
      value={value}
      placeholder={placeholder}
      mode="tags"
      maxTagCount={1}
      style={{ width: '100%' }}
      options={options}
      open={open}
      onDropdownVisibleChange={setOpen}
      onSelect={() => setOpen(false)}
      onChange={(v) => onChange(Array.isArray(v) ? v[v.length - 1] : v)}
    />
  )
}

export default function TypeSettingsModal({
  open, onClose, projectId, type, item, options, imageModels, projectImages, inheritedModel, marketConfig = {}, onSave, onSaveAsTemplate,
}: Props) {
  const [personal, setPersonal] = useState<Record<string, string>>({})
  const [common, setCommon] = useState<Record<string, string>>({ ...COMMON_DEFAULTS })
  const [note, setNote] = useState('')
  const [providerId, setProviderId] = useState<number | null>(null)
  const [modelName, setModelName] = useState<string | null>(null)
  const [modelLabel, setModelLabel] = useState('默认图片模型')
  const [count, setCount] = useState(1)
  const [ratio, setRatio] = useState('自适应尺寸')
  const [resolution, setResolution] = useState('1K')
  const [filling, setFilling] = useState(false)
  const [referenceImages, setReferenceImages] = useState<string[]>([])
  const [galleryOpen, setGalleryOpen] = useState(false)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    if (!open || !type) return
    setPersonal(item?.personal_settings ? { ...item.personal_settings } : {})
    // 通用设置默认值：硬编码兜底 → 外层市场配置 → 用户已保存的手动修改
    const baseCommon = { ...COMMON_DEFAULTS }
    for (const { key } of COMMON_KEYS) {
      const v = marketConfig?.[key]
      if (v) baseCommon[key] = v
    }
    setCommon({ ...baseCommon, ...(item?.common_settings || {}) })
    setNote(item?.note || '')
    setReferenceImages(item?.reference_images ? [...item.reference_images] : [])
    const os = item?.output_settings || {}
    const pid = os.provider_id ?? inheritedModel?.provider_id ?? null
    const mname = os.model_name ?? inheritedModel?.model_name ?? null
    const mlbl = os.model_label ?? inheritedModel?.model_label ?? '默认图片模型'
    setProviderId(pid)
    setModelName(mname)
    setModelLabel(mlbl)
    setCount(os.count || 1)
    setRatio(os.ratio || '自适应尺寸')
    setResolution(os.resolution || '1K')
  }, [open, type, item, inheritedModel, marketConfig])

  if (!type) return null

  const handleAiFill = async () => {
    setFilling(true)
    try {
      const res = await aiFill(projectId, type.id, {
        personal_settings: personal,
        common_settings: common,
        note,
      })
      setPersonal((prev) => {
        const next = { ...prev }
        for (const [k, v] of Object.entries(res.personal_settings || {})) {
          if (!next[k]) next[k] = v
        }
        return next
      })
      setCommon((prev) => {
        const next = { ...prev }
        for (const [k, v] of Object.entries(res.common_settings || {})) {
          if (!next[k]) next[k] = v
        }
        return next
      })
      if (!note && res.note) setNote(res.note)
      message.success('AI 已为你补充建议，可继续修改')
    } catch (e) {
      /* 错误已由 request 统一提示 */
    } finally {
      setFilling(false)
    }
  }

  const buildPayload = () => ({
    type_id: type.id,
    personal_settings: personal,
    common_settings: common,
    output_settings: {
      provider_id: providerId,
      model_name: modelName,
      model_label: modelLabel,
      model: modelLabel,
      count,
      ratio,
      resolution,
    },
    note,
    reference_images: referenceImages,
    product_image: item?.product_image || '',
  })

  const handleSave = () => {
    onSave(buildPayload())
  }

  const handleSaveAsTemplate = () => {
    onSaveAsTemplate({
      ...buildPayload(),
      title: type.title,
    })
  }

  const modelValue =
    providerId != null && modelName
      ? `${providerId}::${modelName}`
      : '__default__'

  const handleModelChange = (val: string) => {
    if (val === '__default__') {
      setProviderId(null)
      setModelName(null)
      setModelLabel('默认图片模型')
      return
    }
    const [pid, mname] = val.split('::')
    const p = imageModels.providers.find((pp) => pp.provider_id === Number(pid))
    setProviderId(Number(pid))
    setModelName(mname)
    setModelLabel(p ? `${p.provider_name} · ${mname}` : mname)
  }

  // 参考图片上传
  const uploadProps: UploadProps = {
    accept: 'image/*',
    showUploadList: false,
    multiple: true,
    beforeUpload: (file) => {
      const isImage = file.type.startsWith('image/')
      if (!isImage) { message.error('请上传图片文件'); return Upload.LIST_IGNORE }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      if (referenceImages.length >= 4) {
        message.warning('最多上传 4 张参考图片')
        onError?.(new Error('超过 4 张'))
        return
      }
      setUploading(true)
      try {
        const res = await uploadImages(projectId, [file as File])
        const img = res[0]?.images?.find((i: GalleryImage) => i.url) || res[0]?.images?.[0]
        if (img?.url) {
          setReferenceImages((prev) => [...prev, img.url].slice(0, 4))
          message.success('上传成功')
          onSuccess?.(img.url)
        } else {
          throw new Error('上传失败')
        }
      } catch (e) {
        message.error('上传失败，请重试')
        onError?.(e as Error)
      } finally {
        setUploading(false)
      }
    },
  }

  const removeReferenceImage = (idx: number) => {
    setReferenceImages((prev) => {
      const next = [...prev]
      next.splice(idx, 1)
      return next
    })
  }

  const addFromGallery = (url: string) => {
    if (referenceImages.length >= 4) {
      message.warning('最多选择 4 张参考图片')
      return
    }
    setReferenceImages((prev) => [...prev, url].slice(0, 4))
    setGalleryOpen(false)
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={typeof window !== 'undefined' && window.innerWidth < 820 ? '100%' : 960}
      className="g-modal type-settings-modal"
      destroyOnClose
      title={null}
    >
      <div className="modal-inner">
        <div className="modal-header">
          <h2>{type.title} 属性设置</h2>
          <p>以下选项无需全部填写，选项之间可能会有冲突，请注意修改</p>
        </div>

        <div className="modal-body">
          {/* 左栏：个性化 + 通用 */}
          <div className="modal-col">
            <div className="ms-block">
              <h4>
                个性化设置
                <button className="btn-aifill" onClick={handleAiFill} disabled={filling}>
                  {filling ? '填充中…' : '✨ AI帮填(免费)'}
                </button>
              </h4>
              <p className="ms-note">（选填项，可手动填写或者使用「AI帮填」）</p>
              <div className="ms-fields">
                {type.personal.map((f) => (
                  <div className="pf-row" key={f.label}>
                    <label>{f.label}</label>
                  {f.options && f.options.length > 0 ? (
                    <SingleTagSelect
                      value={personal[f.label] || undefined}
                      placeholder={f.placeholder || '请选择，或直接输入'}
                      options={f.options.map((o) => ({ label: o, value: o }))}
                      onChange={(v) => setPersonal((p) => ({ ...p, [f.label]: v }))}
                    />
                  ) : f.label === '规格参数原文' ? (
                    <Input.TextArea
                      rows={3}
                      value={personal[f.label] || ''}
                      placeholder={f.placeholder || '请粘贴具体规格/尺码数据'}
                      onChange={(e) => setPersonal((p) => ({ ...p, [f.label]: e.target.value }))}
                    />
                  ) : (
                    <Input
                      value={personal[f.label] || ''}
                      placeholder={f.placeholder || '请选择，或直接输入'}
                      onChange={(e) => setPersonal((p) => ({ ...p, [f.label]: e.target.value }))}
                    />
                  )}
                  </div>
                ))}
              </div>
            </div>

            <div className="ms-block">
              <h4>
                通用设置
                <button className="btn-aifill" onClick={handleAiFill} disabled={filling}>
                  {filling ? '填充中…' : '✨ AI帮填(免费)'}
                </button>
              </h4>
              <p className="ms-note">（选填项，可手动填写或者使用「AI帮填」）</p>
              <div className="ms-fields">
                {COMMON_KEYS.map(({ key, label }) => (
                  <div className="pf-row" key={key}>
                    <label>{label}</label>
                    <SingleTagSelect
                      value={common[key] || undefined}
                      placeholder="请选择，或直接输入"
                      options={(options.common[key] || []).map((o: string) => ({ label: o, value: o }))}
                      onChange={(v) => setCommon((c) => ({ ...c, [key]: v }))}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 右栏：补充说明 + 出图设置 + 参考图片 */}
          <div className="modal-col">
            <div className="ms-block">
              <h4>补充说明</h4>
              <Input.TextArea
                rows={3}
                maxLength={2000}
                showCount
                value={note}
                placeholder="一句话讲清产品优势，AI 将据此生成文案与构图建议"
                onChange={(e) => setNote(e.target.value)}
              />
            </div>

            <div className="ms-block">
              <h4>出图设置</h4>
              <div className="ms-fields">
                <div className="pf-row">
                  <label>模型 <span className="ms-note" style={{ display: 'inline' }}>（来自 AI 提供商图片模型）</span></label>
                  <Select
                    value={modelValue}
                    style={{ width: '100%' }}
                    placeholder="默认（自动选择）"
                    popupMatchSelectWidth={false}
                    dropdownStyle={{ minWidth: 320 }}
                    options={[
                      { label: '默认（自动选择 AI 提供商默认图片模型）', value: '__default__', title: '默认（自动选择 AI 提供商默认图片模型）' },
                      ...imageModels.providers.map((p) => ({
                        label: p.provider_name,
                        options: p.models.map((m) => ({
                          label: m.model_name,
                          value: `${p.provider_id}::${m.model_name}`,
                          title: `${p.provider_name} · ${m.model_name}`,
                        })),
                      })),
                    ]}
                    onChange={handleModelChange}
                  />
                  {imageModels.providers.length === 0 && (
                    <span className="ms-note">尚未配置 AI 提供商的图片生成模型，可在「AI 提供商」中添加。</span>
                  )}
                </div>
                <div className="pf-row">
                  <label>出图数量</label>
                  <div className="g-stepper">
                    <button onClick={() => setCount((c) => Math.max(1, c - 1))}>−</button>
                    <span>{count}</span>
                    <button onClick={() => setCount((c) => c + 1)}>+</button>
                  </div>
                </div>
                {type.hasResolution ? (
                  <div className="pf-row">
                    <label>分辨率</label>
                    <div className="g-res-btns">
                      {(options.output.promo_resolution || []).map((r: string) => (
                        <button key={r} className={resolution === r ? 'on' : ''} onClick={() => setResolution(r)}>{r}</button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="pf-row">
                    <label>图片比例</label>
                    <Select
                      value={ratio}
                      style={{ width: '100%' }}
                      options={(options.output.ratio || []).map((r: string) => ({ label: r, value: r }))}
                      onChange={setRatio}
                    />
                  </div>
                )}
              </div>
            </div>

            <div className="ms-block">
              <h4>参考图片 <span className="ms-note">（可选，最多可上传 4 张）</span></h4>
              <div className="ref-upload">
                <div className="ref-upload-box">
                  <div className="ref-upload-actions">
                    <Upload {...uploadProps} disabled={uploading || referenceImages.length >= 4}>
                      <button className="ref-upload-btn" disabled={uploading || referenceImages.length >= 4}>
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                          <polyline points="17 8 12 3 7 8" />
                          <line x1="12" y1="3" x2="12" y2="15" />
                        </svg>
                        <span>{uploading ? '上传中…' : '本地上传'}</span>
                      </button>
                    </Upload>
                    <button className="ref-lib-btn" onClick={() => setGalleryOpen(true)} disabled={referenceImages.length >= 4}>
                      图片库
                    </button>
                  </div>
                  <div className="ref-preview-list">
                    {referenceImages.map((url, idx) => (
                      <div className="ref-preview" key={`${url}-${idx}`}>
                        <img src={url} alt="参考图片" />
                        <button className="ref-remove" onClick={() => removeReferenceImage(idx)} title="移除">✕</button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-confirm" onClick={handleSave}>设置完成并关闭</button>
          <button className="btn-template" onClick={handleSaveAsTemplate}>另存为模板</button>
        </div>
      </div>

      <Modal
        open={galleryOpen}
        onCancel={() => setGalleryOpen(false)}
        footer={null}
        title={'图片库'}
        width={720}
        className="g-modal gallery-picker-modal"
      >
        <div className="gallery-picker">
          {projectImages.length === 0 ? (
            <p className="gp-empty">暂无项目图片，请先上传产品图。</p>
          ) : (
            <div className="gp-grid">
              {projectImages.map((img) => (
                <div className="gp-item" key={img.id} onClick={() => addFromGallery(img.url)}>
                  <img src={img.url} alt={img.filename} />
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>
    </Modal>
  )
}
