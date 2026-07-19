import { useEffect, useRef, useState } from 'react'
import { Drawer, Empty, Input, Select, message, Modal } from 'antd'
import type { GalleryOptions, GalleryType, GalleryTemplate, GalleryImageModelsResponse, GalleryPlanItem } from '@/services/gallery'

interface Props {
  open: boolean
  onClose: () => void
  types: GalleryType[]
  options: GalleryOptions
  templates: GalleryTemplate[]
  imageModels: GalleryImageModelsResponse
  initialChecked: string[]
  onConfirm: (checkedIds: string[]) => void
  onQuickAdd: (checkedIds: string[]) => void
  onApplyTemplate: (templateId: number) => void
  onDeleteTemplate: (templateId: number) => void
  onRenameTemplate: (templateId: number, newName: string) => Promise<void>
  onCreateCustomTask: (payload: {
    name: string
    description: string
    files: File[]
    provider_id: number | null
    model_name: string | null
    model_label: string
    resolution: string
    ratio: string
    count: number
  }) => Promise<void>
  /** 编辑模式：传入此项时，自定义表单预填其设置，提交走 onUpdateCustomTask */
  editItem?: GalleryPlanItem | null
  onUpdateCustomTask: (payload: {
    name: string
    description: string
    files: File[]
    provider_id: number | null
    model_name: string | null
    model_label: string
    resolution: string
    ratio: string
    count: number
    reference_images: string[]
  }) => Promise<void>
}

type Tab = '推荐类型' | '自定义子任务' | '已保存模板'

const { TextArea } = Input

export default function PlannerDrawer({
  open, onClose, types, options, templates, imageModels, initialChecked,
  onConfirm, onQuickAdd, onApplyTemplate, onDeleteTemplate, onRenameTemplate, onCreateCustomTask,
  editItem, onUpdateCustomTask,
}: Props) {
  const [tab, setTab] = useState<Tab>('推荐类型')
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [submitting, setSubmitting] = useState(false)

  // 自定义子任务表单
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [providerId, setProviderId] = useState<number | null>(null)
  const [modelName, setModelName] = useState<string | null>(null)
  const [modelLabel, setModelLabel] = useState<string>('默认图片模型')
  const [resolution, setResolution] = useState<string>(options?.output?.resolution?.[0] || '1K')
  const [ratio, setRatio] = useState<string>(options?.output?.ratio?.[0] || '自适应尺寸')
  const [count, setCount] = useState<number>(options?.output?.count_default || 1)
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  // 编辑模式下保留的已有参考图（URL），可移除；新上传图在 files 中
  const [existingRefs, setExistingRefs] = useState<string[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const outputOptions = options?.output || {}
  const resolutionOpts = (outputOptions.resolution || []).map((o: string) => ({ label: o, value: o }))
  const ratioOpts = (outputOptions.ratio || []).map((o: string) => ({ label: o, value: o }))
  const showTypes = types.filter((t) => t.id !== 'custom')

  // 当前模型下拉值：与 TypeSettingsModal 保持同一规则
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

  useEffect(() => {
    if (open) {
      setChecked(new Set(initialChecked))
      if (editItem) {
        // 编辑模式：切到「自定义子任务」并预填该项现有设置
        setTab('自定义子任务')
        setName(editItem.personal_settings?.['任务名称'] || '')
        setDescription(editItem.note || '')
        setProviderId((editItem.output_settings?.provider_id as number) ?? null)
        setModelName((editItem.output_settings?.model_name as string) ?? null)
        setModelLabel(editItem.output_settings?.model_label || editItem.output_settings?.model || '默认图片模型')
        setResolution(editItem.output_settings?.resolution || outputOptions.resolution?.[0] || '1K')
        setRatio(editItem.output_settings?.ratio || outputOptions.ratio?.[0] || '自适应尺寸')
        setCount(Number(editItem.output_settings?.count) || outputOptions.count_default || 1)
        setFiles([])
        setPreviews([])
        setExistingRefs(editItem.reference_images || [])
      } else {
        setTab('推荐类型')
        resetCustomForm()
      }
    }
  }, [open, initialChecked, editItem])

  const resetCustomForm = () => {
    setName('')
    setDescription('')
    setProviderId(null)
    setModelName(null)
    setModelLabel('默认图片模型')
    setResolution(outputOptions.resolution?.[0] || '1K')
    setRatio(outputOptions.ratio?.[0] || '自适应尺寸')
    setCount(outputOptions.count_default || 1)
    setFiles([])
    setPreviews([])
    setExistingRefs([])
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
    const remain = Math.max(0, 4 - files.length - existingRefs.length)
    const incoming = Array.from(fileList).slice(0, remain)
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

  const removeExistingRef = (idx: number) => {
    setExistingRefs((prev) => prev.filter((_, i) => i !== idx))
  }

  const handleSubmitCustom = async () => {
    const taskName = name.trim() || '自定义子任务'
    if (!description.trim()) {
      message.warning('请填写需求描述 / 详细提示词')
      return
    }
    setSubmitting(true)
    try {
      const basePayload = {
        name: taskName,
        description: description.trim(),
        files,
        provider_id: providerId,
        model_name: modelName,
        model_label: modelLabel,
        resolution,
        ratio,
        count: Math.max(1, Math.min(count, 50)),
      }
      if (editItem) {
        await onUpdateCustomTask({ ...basePayload, reference_images: existingRefs })
        message.success('已更新自定义子任务')
      } else {
        await onCreateCustomTask(basePayload)
        message.success('已添加自定义子任务')
      }
      resetCustomForm()
      onClose()
    } catch (e) {
      console.error('[gallery] handleSubmitCustom failed:', e)
      // request.ts 已统一弹错误 toast；此处仅兜底显示一句简短提示，避免静默失败
      message.error(e instanceof Error ? e.message : (editItem ? '更新自定义子任务失败，请重试' : '添加自定义子任务失败，请重试'))
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
                  {existingRefs.map((url, idx) => (
                    <div key={`ref-${idx}`} className="ctf-preview">
                      <img src={url} alt="" />
                      <button className="ctf-remove" onClick={() => removeExistingRef(idx)} title="移除已有参考图">✕</button>
                    </div>
                  ))}
                  {previews.map((url, idx) => (
                    <div key={`new-${idx}`} className="ctf-preview">
                      <img src={url} alt="" />
                      <button className="ctf-remove" onClick={() => removeImage(idx)} title="移除">✕</button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="ctf-grid">
                <div className="ctf-field">
                  <label><span className="ctf-icon">⚙</span>模型 <span style={{ fontSize: 12, color: 'var(--gb-ink-faint)', fontWeight: 400 }}>（AI 提供商图片模型）</span></label>
                  <Select
                    value={modelValue}
                    placeholder="默认（自动选择）"
                    style={{ width: '100%' }}
                    options={[
                      { label: '默认（自动选择 AI 提供商默认图片模型）', value: '__default__' },
                      ...imageModels.providers.map((p) => ({
                        label: p.provider_name,
                        options: p.models.map((m) => ({ label: m.model_name, value: `${p.provider_id}::${m.model_name}` })),
                      })),
                    ]}
                    onChange={handleModelChange}
                  />
                  {imageModels.providers.length === 0 && (
                    <span style={{ fontSize: 12, color: 'var(--g-warn, #E0A106)', marginTop: 4, display: 'block' }}>
                      尚未配置 AI 提供商的图片生成模型，将使用默认模型。
                    </span>
                  )}
                </div>
                <div className="ctf-field">
                  <label><span className="ctf-icon">📐</span>分辨率</label>
                  <Select options={resolutionOpts} value={resolution} onChange={setResolution} style={{ width: '100%' }} />
                </div>
                <div className="ctf-field">
                  <label><span className="ctf-icon">⬜</span>图片比例</label>
                  <Select options={ratioOpts} value={ratio} onChange={setRatio} style={{ width: '100%' }} />
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
                {editItem ? '保存修改' : '确认添加任务'}
              </button>
            </div>
          )}

          {tab === '已保存模板' && (
            templates.length === 0 ? (
              <Empty description="暂无已保存模板" style={{ marginTop: 40 }} />
            ) : (
              <div className="template-list">
                {templates.map((tpl) => (
                  <div
                    key={tpl.id}
                    className="template-card"
                    onClick={() => { onApplyTemplate(tpl.id); onClose() }}
                    title="点击添加到出图规划列表"
                  >
                    {tpl.cover_url && (
                      <div className="template-cover">
                        <img src={tpl.cover_url} alt="" />
                      </div>
                    )}
                    <div className="template-info">
                      <h4>{tpl.name}</h4>
                      <p>
                        包含 {(tpl.payload?.plan_items?.length) || 0} 个出图类型：
                        {(tpl.payload?.plan_items || []).map((it: any) => it.title || it.type_id).join('、')}
                      </p>
                    </div>
                    <div className="template-actions">
                      <button
                        className="tpl-btn-edit"
                        title="修改模板名称"
                        onClick={(e) => {
                          e.stopPropagation()
                          const newName = window.prompt('修改模板名称', tpl.name)
                          if (newName && newName.trim() && newName.trim() !== tpl.name) {
                            onRenameTemplate(tpl.id, newName.trim())
                          }
                        }}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                      <button
                        className="tpl-btn-delete"
                        title="删除模板"
                        onClick={(e) => {
                          e.stopPropagation()
                          Modal.confirm({
                            title: '确认删除模板？',
                            content: `将删除模板「${tpl.name}」，此操作不可恢复。`,
                            okText: '删除',
                            okType: 'danger',
                            cancelText: '取消',
                            onOk: () => onDeleteTemplate(tpl.id),
                          })
                        }}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3,6 5,6 21,6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m2 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
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
