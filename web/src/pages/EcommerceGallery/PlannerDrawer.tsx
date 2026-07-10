import { useEffect, useRef, useState } from 'react'
import { Drawer, Empty, Input, Select, message } from 'antd'
import type { GalleryOptions, GalleryType, GalleryTemplate } from '@/services/gallery'

interface Props {
  open: boolean
  onClose: () => void
  types: GalleryType[]
  options: GalleryOptions
  templates: GalleryTemplate[]
  initialChecked: string[]
  onConfirm: (checkedIds: string[]) => void
  onQuickAdd: (checkedIds: string[]) => void
  onApplyTemplate: (templateId: number) => void
  onDeleteTemplate: (templateId: number) => void
  onCreateCustomTask: (payload: {
    name: string
    description: string
    files: File[]
    model: string
    resolution: string
    ratio: string
    count: number
  }) => Promise<void>
}

type Tab = '推荐类型' | '自定义子任务' | '已保存模板'

const { TextArea } = Input

export default function PlannerDrawer({
  open, onClose, types, options, templates, initialChecked,
  onConfirm, onQuickAdd, onApplyTemplate, onDeleteTemplate, onCreateCustomTask,
}: Props) {
  const [tab, setTab] = useState<Tab>('推荐类型')
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [submitting, setSubmitting] = useState(false)

  // 自定义子任务表单
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [model, setModel] = useState<string>(options?.output?.model?.[0] || 'Banana-pro')
  const [resolution, setResolution] = useState<string>(options?.output?.resolution?.[0] || '1K')
  const [ratio, setRatio] = useState<string>(options?.output?.ratio?.[0] || '自适应尺寸')
  const [count, setCount] = useState<number>(options?.output?.count_default || 1)
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const outputOptions = options?.output || {}
  const modelOpts = (outputOptions.model || []).map((o: string) => ({ label: o, value: o }))
  const resolutionOpts = (outputOptions.resolution || []).map((o: string) => ({ label: o, value: o }))
  const ratioOpts = (outputOptions.ratio || []).map((o: string) => ({ label: o, value: o }))
  const showTypes = types.filter((t) => t.id !== 'custom')

  useEffect(() => {
    if (open) {
      setChecked(new Set(initialChecked))
      setTab('推荐类型')
      resetCustomForm()
    }
  }, [open, initialChecked])

  const resetCustomForm = () => {
    setName('')
    setDescription('')
    setModel(outputOptions.model?.[0] || 'Banana-pro')
    setResolution(outputOptions.resolution?.[0] || '1K')
    setRatio(outputOptions.ratio?.[0] || '自适应尺寸')
    setCount(outputOptions.count_default || 1)
    setFiles([])
    setPreviews([])
  }

  const toggle = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return
    const incoming = Array.from(fileList).slice(0, 4 - files.length)
    if (incoming.length === 0) return
    const next = [...files, ...incoming].slice(0, 4)
    setFiles(next)
    setPreviews(next.map((f) => URL.createObjectURL(f)))
  }

  const removeImage = (idx: number) => {
    const next = [...files]
    next.splice(idx, 1)
    setFiles(next)
    setPreviews(next.map((f) => URL.createObjectURL(f)))
  }

  const handleSubmitCustom = async () => {
    const taskName = name.trim() || '自定义子任务'
    if (!description.trim()) {
      message.warning('请填写需求描述 / 详细提示词')
      return
    }
    setSubmitting(true)
    try {
      await onCreateCustomTask({
        name: taskName,
        description: description.trim(),
        files,
        model,
        resolution,
        ratio,
        count: Math.max(1, Math.min(count, 50)),
      })
      message.success('已添加自定义子任务')
      resetCustomForm()
      onClose()
    } catch (e) {
      // 统一错误在父层提示
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      width={typeof window !== 'undefined' && window.innerWidth < 520 ? '100%' : 520}
      title={null}
      closable={false}
      className="g-drawer"
      styles={{ body: { padding: 0 } }}
    >
      <div className="drawer-wrap">
        <div className="drawer-head">
          <div className="drawer-tabs">
            {(['推荐类型', '自定义子任务', '已保存模板'] as Tab[]).map((t) => (
              <button
                key={t}
                className={`drawer-tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <button className="drawer-close" onClick={onClose}>✕</button>
        </div>

        <div className="drawer-body">
          {tab === '推荐类型' && (
            <div className="drawer-grid">
              {showTypes.map((t) => (
                <div
                  key={t.id}
                  className={`dg-card ${checked.has(t.id) ? 'checked' : ''}`}
                  onClick={() => toggle(t.id)}
                >
                  <div className="dg-card-text">
                    <h4>{t.title}</h4>
                    <p>{t.desc}</p>
                  </div>
                  <div className="dg-cb">{checked.has(t.id) ? '✓' : ''}</div>
                </div>
              ))}
            </div>
          )}

          {tab === '自定义子任务' && (
            <div className="custom-task-form">
              <div className="ctf-field">
                <label><span className="ctf-icon">T</span>任务名称</label>
                <Input
                  placeholder='可选，不填默认"自定义子任务"'
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={100}
                />
              </div>

              <div className="ctf-field">
                <label><span className="ctf-icon">✨</span>需求描述 / 详细提示词</label>
                <TextArea
                  placeholder="请输入该任务需要生成的画面描述"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={5}
                  maxLength={2000}
                  showCount
                />
              </div>

              <div className="ctf-field">
                <label><span className="ctf-icon">🖼</span>参考图片 <span className="ctf-tip">（可选，最多 4 张）</span></label>
                <div className="ctf-upload">
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/*"
                    multiple
                    hidden
                    onChange={(e) => handleFiles(e.target.files)}
                  />
                  <button className="ctf-upload-btn" onClick={() => fileRef.current?.click()}>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    <span>本地上传</span>
                  </button>
                  <button className="ctf-lib-btn" onClick={() => message.info('图片库功能开发中')}>图片库</button>
                </div>
                {previews.length > 0 && (
                  <div className="ctf-previews">
                    {previews.map((url, idx) => (
                      <div key={idx} className="ctf-preview">
                        <img src={url} alt="" />
                        <button className="ctf-remove" onClick={() => removeImage(idx)} title="移除">✕</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="ctf-grid">
                <div className="ctf-field">
                  <label><span className="ctf-icon">⚙</span>模型</label>
                  <Select options={modelOpts} value={model} onChange={setModel} />
                </div>
                <div className="ctf-field">
                  <label><span className="ctf-icon">📐</span>分辨率</label>
                  <Select options={resolutionOpts} value={resolution} onChange={setResolution} />
                </div>
                <div className="ctf-field">
                  <label><span className="ctf-icon">⬜</span>图片比例</label>
                  <Select options={ratioOpts} value={ratio} onChange={setRatio} />
                </div>
                <div className="ctf-field">
                  <label><span className="ctf-icon">🖼</span>出图数量</label>
                  <div className="ctf-stepper">
                    <button onClick={() => setCount((c) => Math.max(1, c - 1))}>−</button>
                    <span>{count}</span>
                    <button onClick={() => setCount((c) => Math.min(50, c + 1))}>+</button>
                  </div>
                </div>
              </div>

              <button
                className="ctf-submit"
                disabled={submitting}
                onClick={handleSubmitCustom}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" />
                  <path d="M8 12l3 3 5-6" />
                </svg>
                确认添加任务
              </button>
            </div>
          )}

          {tab === '已保存模板' && (
            templates.length === 0 ? (
              <Empty description="暂无已保存模板" style={{ marginTop: 40 }} />
            ) : (
              <div className="template-list">
                {templates.map((tpl) => (
                  <div key={tpl.id} className="template-card">
                    <div className="template-info">
                      <h4>{tpl.name}</h4>
                      <p>
                        包含 {(tpl.payload?.plan_items?.length) || 0} 个出图类型：
                        {(tpl.payload?.plan_items || []).map((it: any) => it.title || it.type_id).join('、')}
                      </p>
                    </div>
                    <div className="template-actions">
                      <button
                        className="template-use"
                        onClick={() => { onApplyTemplate(tpl.id); onClose() }}
                      >选用该任务</button>
                      <button
                        className="template-delete"
                        title="删除模板"
                        onClick={() => onDeleteTemplate(tpl.id)}
                      >🗑</button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </div>

        {tab === '推荐类型' && (
          <div className="drawer-foot">
            <span className="df-count">已勾选 <b>{checked.size}</b> 个推荐类型</span>
            <div className="df-actions">
              <button className="btn-df-cancel" onClick={onClose}>取消</button>
              <button
                className="btn-df-quick"
                onClick={() => {
                  if (checked.size === 0) {
                    message.warning('请至少选择一个策划类型')
                    return
                  }
                  onQuickAdd([...checked])
                }}
              >⚡ 极速添加 ({checked.size})</button>
              <button
                className="btn-df-confirm"
                onClick={() => {
                  if (checked.size === 0) {
                    message.warning('请至少选择一个策划类型')
                    return
                  }
                  onConfirm([...checked])
                }}
              >AI 智能策划 ({checked.size})</button>
            </div>
          </div>
        )}
      </div>
    </Drawer>
  )
}
