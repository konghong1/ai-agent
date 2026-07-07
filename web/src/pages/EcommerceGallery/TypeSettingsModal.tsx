import { useEffect, useState } from 'react'
import { Modal, Input, Select, message } from 'antd'
import type { GalleryType, GalleryOptions, GalleryPlanItem, GalleryImage } from '@/services/gallery'
import { aiFill } from '@/services/gallery'

interface Props {
  open: boolean
  onClose: () => void
  projectId: number
  type: GalleryType | null
  item: GalleryPlanItem | undefined
  options: GalleryOptions
  projectImages: GalleryImage[]
  onSave: (payload: {
    type_id: string
    personal_settings: Record<string, string>
    common_settings: Record<string, string>
    output_settings: Record<string, any>
    note: string
    reference_images: string[]
  }, asTemplate?: boolean) => void
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
  copy_need: '核心卖点文案',
  tone_tendency: '高饱和色调',
}

export default function TypeSettingsModal({
  open, onClose, projectId, type, item, options, projectImages, onSave,
}: Props) {
  const [personal, setPersonal] = useState<Record<string, string>>({})
  const [common, setCommon] = useState<Record<string, string>>({ ...COMMON_DEFAULTS })
  const [note, setNote] = useState('')
  const [model, setModel] = useState('Banana-pro')
  const [count, setCount] = useState(1)
  const [ratio, setRatio] = useState('自适应尺寸')
  const [resolution, setResolution] = useState('1K')
  const [refs, setRefs] = useState<string[]>([])
  const [filling, setFilling] = useState(false)

  useEffect(() => {
    if (!open || !type) return
    setPersonal(item?.personal_settings ? { ...item.personal_settings } : {})
    setCommon({ ...COMMON_DEFAULTS, ...(item?.common_settings || {}) })
    setNote(item?.note || '')
    const os = item?.output_settings || {}
    setModel(os.model || 'Banana-pro')
    setCount(os.count || 1)
    setRatio(os.ratio || (type.hasResolution ? '自动' : '自适应尺寸'))
    setResolution(os.resolution || '1K')
    setRefs(item?.reference_images || [])
  }, [open, type, item])

  if (!type) return null

  const handleAiFill = async () => {
    setFilling(true)
    try {
      const res = await aiFill(projectId, type.id, {
        personal_settings: personal,
        common_settings: common,
        note,
      })
      // 仅填充为空的项，避免覆盖用户已填内容
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

  const toggleRef = (filename: string) => {
    setRefs((prev) => (prev.includes(filename) ? prev.filter((f) => f !== filename) : [...prev, filename]))
  }

  const handleSave = (asTemplate = false) => {
    onSave({
      type_id: type.id,
      personal_settings: personal,
      common_settings: common,
      output_settings: { model, count, ratio, resolution },
      note,
      reference_images: refs,
    }, asTemplate)
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={typeof window !== 'undefined' && window.innerWidth < 820 ? '100%' : 960}
      className="g-modal"
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
                    <Input
                      value={personal[f.label] || ''}
                      placeholder={f.placeholder || '请选择，或直接输入'}
                      onChange={(e) => setPersonal((p) => ({ ...p, [f.label]: e.target.value }))}
                    />
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
                    <Select
                      value={common[key] || undefined}
                      placeholder="请选择，或直接输入"
                      mode="tags"
                      style={{ width: '100%' }}
                      options={(options.common[key] || []).map((o) => ({ label: o, value: o }))}
                      onChange={(v: string | string[]) => setCommon((c) => ({ ...c, [key]: Array.isArray(v) ? v[v.length - 1] : v }))}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 右栏：补充说明 + 出图设置 + 参考图 */}
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
                  <label>模型</label>
                  <div className="g-model-tabs">
                    {(options.output.model || []).map((m: string) => (
                      <button key={m} className={model === m ? 'on' : ''} onClick={() => setModel(m)}>{m}</button>
                    ))}
                  </div>
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
              <h4>参考图片</h4>
              <p className="ms-note">从已上传的产品图中选择作为参考（可选）</p>
              <div className="ref-upload">
                {projectImages.map((img) => (
                  <div
                    key={img.id}
                    className="ref-thumb"
                    style={{ cursor: 'pointer', outline: refs.includes(img.filename) ? '2px solid var(--g-brand)' : 'none' }}
                    onClick={() => toggleRef(img.filename)}
                    title={refs.includes(img.filename) ? '取消参考' : '设为参考'}
                  >
                    <img src={img.url} alt="" />
                  </div>
                ))}
                {projectImages.length === 0 && (
                  <span style={{ fontSize: 12, color: 'var(--ice-text-secondary)' }}>请先在左侧上传产品图</span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-confirm" onClick={() => handleSave(false)}>设置完成并关闭</button>
          <button className="btn-template" onClick={() => handleSave(true)}>另存为模板</button>
        </div>
      </div>
    </Modal>
  )
}
