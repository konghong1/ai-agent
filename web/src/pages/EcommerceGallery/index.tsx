import { useCallback, useEffect, useRef, useState } from 'react'
import { message, Modal, Spin, Input, Select, Image } from 'antd'
import {
  getTypes, getShowcases, getDraft, getMyRecords, getTemplates,
  getImageModels,
  uploadImages, deleteImage, updateProject,
  createPlanItem, updatePlanItem, deletePlanItem,
  generate, createTemplate, deleteTemplate, applyTemplate, updateTemplate,
} from '@/services/gallery'
import type {
  GalleryType, GalleryOptions, GalleryProject, GalleryShowcase,
  GalleryRecord, GalleryTemplate, GalleryPlanItem,
  GalleryImageModelsResponse,
} from '@/services/gallery'
import PlannerDrawer from './PlannerDrawer'
import SaveTemplateModal from './SaveTemplateModal'
import TypeSettingsModal from './TypeSettingsModal'
import { PlanRow } from '@/components/gallery'
import './gallery.css'

function typeTitle(types: GalleryType[], id: string): string {
  return types.find((t) => t.id === id)?.title || id
}

function isRealImage(url: string | null | undefined): boolean {
  if (!url) return false
  const u = url.trim()
  if (!u.startsWith('http') && !u.startsWith('data:')) return false
  const lower = u.toLowerCase()
  // 过滤掉常见占位 / 渐变占位图
  if (lower.includes('placeholder') || lower.includes('gradient') || lower.includes('svg') || lower.includes('svg+xml')) return false
  return true
}

function fallbackImg(seed: string, w: number, h: number): string {
  return `https://picsum.photos/seed/${seed}/${w}/${h}`
}

function caseStripImages(sc: GalleryShowcase): string[] {
  const orig = isRealImage(sc.original_url) ? sc.original_url : fallbackImg(`${sc.id}-orig`, 200, 200)
  const rest = (sc.image_urls || []).slice(0, 3).map((u, i) =>
    isRealImage(u) ? u : fallbackImg(`${sc.id}-${i}`, 200, 200)
  )
  while (rest.length < 3) rest.push(fallbackImg(`${sc.id}-${rest.length}`, 200, 200))
  return [orig, ...rest]
}

export default function EcommerceGallery() {
  const [types, setTypes] = useState<GalleryType[]>([])
  const [options, setOptions] = useState<GalleryOptions>({ common: {}, market: {}, output: {}, showcase_categories: [] })
  const [project, setProject] = useState<GalleryProject | null>(null)
  const [showcases, setShowcases] = useState<GalleryShowcase[]>([])
  const [showcaseCat, setShowcaseCat] = useState('全部')
  const [records, setRecords] = useState<GalleryRecord[]>([])
  const [templates, setTemplates] = useState<GalleryTemplate[]>([])
  const [imageModels, setImageModels] = useState<GalleryImageModelsResponse>({ providers: [], default_image_model: null })

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [activeType, setActiveType] = useState<GalleryType | null>(null)
  const [activeItem, setActiveItem] = useState<GalleryPlanItem | undefined>(undefined)
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false)
  const [pendingTemplate, setPendingTemplate] = useState<{
    type_id: string
    title: string
    personal_settings: Record<string, string>
    common_settings: Record<string, string>
    output_settings: Record<string, any>
    note: string
  } | null>(null)

  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<null | {
    total_images: number; total_points: number; total_minutes: number; records: GalleryRecord[]
  }>(null)
  const [loading, setLoading] = useState(true)

  const [areaTab, setAreaTab] = useState<'results' | 'cases'>('results')
  const [warnClosed, setWarnClosed] = useState(false)

  const fileRef = useRef<HTMLInputElement>(null)

  const refreshProject = useCallback(async () => {
    const p = await getDraft()
    setProject(p)
    return p
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [t, p, sc, rec, tpl, im] = await Promise.all([
        getTypes(), getDraft(), getShowcases(), getMyRecords(), getTemplates(), getImageModels(),
      ])
      setTypes(t.types)
      setOptions(t.options)
      setProject(p)
      setShowcases(sc)
      setRecords(rec)
      setTemplates(tpl)
      setImageModels(im)
    } catch (e) {
      /* request 已统一提示 */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  // ── 上传产品图 ──
  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0 || !project) return
    const files = Array.from(fileList)
    try {
      const res = await uploadImages(project.id, files)
      if (Array.isArray(res) && res[0]) setProject(res[0])
      message.success(`已上传 ${files.length} 张产品图`)
    } catch (e) { /* 已提示 */ }
  }

  const handleDeleteImage = async (imageId: number) => {
    if (!project) return
    try {
      await deleteImage(project.id, imageId)
      await refreshProject()
    } catch (e) { /* 已提示 */ }
  }

  // ── 策划台 ──
  const openDrawer = () => setDrawerOpen(true)

  // 极速添加：直接加入规划列表，不打开属性设置弹窗
  const quickAddDrawer = async (checkedIds: string[]) => {
    if (!project) return
    const existing = new Set(project.plan_items.map((i) => i.type_id))
    const toAdd = checkedIds.filter((id) => !existing.has(id))
    if (toAdd.length === 0) {
      message.info('所选类型已在规划列表中')
      setDrawerOpen(false)
      return
    }
    try {
      for (const id of toAdd) {
        await createPlanItem(project.id, { type_id: id })
      }
      await refreshProject()
      message.success(`已极速添加 ${toAdd.length} 个类型到规划列表`)
      setDrawerOpen(false)
    } catch (e) { /* 已提示 */ }
  }

  const confirmDrawer = async (checkedIds: string[]) => {
    if (!project) return
    const existing = new Set(project.plan_items.map((i) => i.type_id))
    const toAdd = checkedIds.filter((id) => !existing.has(id))
    try {
      for (const id of toAdd) {
        await createPlanItem(project.id, { type_id: id })
      }
      const p = await refreshProject()
      message.success(toAdd.length ? `已添加 ${toAdd.length} 个策划类型` : '策划类型已更新')
      setDrawerOpen(false)
      // 打开第一个新类型的设置弹窗，引导用户完善属性
      if (toAdd.length) {
        const t = types.find((x) => x.id === toAdd[0])
        const it = p.plan_items.find((i) => i.type_id === toAdd[0])
        setActiveType(t || null)
        setActiveItem(it)
        setModalOpen(true)
      }
    } catch (e) { /* 已提示 */ }
  }

  // 自定义子任务：上传参考图 + 创建 custom 类型策划项
  const createCustomTask = async (payload: {
    name: string
    description: string
    files: File[]
    provider_id: number | null
    model_name: string | null
    model_label: string
    resolution: string
    ratio: string
    count: number
  }) => {
    if (!project) return
    let referenceImages: string[] = []
    if (payload.files.length > 0) {
      const res = await uploadImages(project.id, payload.files)
      const latestProject = res[0] || project
      const images = latestProject.images || []
      referenceImages = images.slice(-payload.files.length).map((img: any) => img.url)
    }
    await createPlanItem(project.id, {
      type_id: 'custom',
      note: payload.description,
      personal_settings: { '任务名称': payload.name },
      output_settings: {
        provider_id: payload.provider_id,
        model_name: payload.model_name,
        model_label: payload.model_label,
        model: payload.model_label,
        resolution: payload.resolution,
        ratio: payload.ratio,
        count: payload.count,
      },
      reference_images: referenceImages,
    })
    await refreshProject()
  }

  // ── 属性设置弹窗 ──
  const openSettings = (typeId: string) => {
    const t = types.find((x) => x.id === typeId) || null
    const it = project?.plan_items.find((i) => i.type_id === typeId)
    setActiveType(t)
    setActiveItem(it)
    setModalOpen(true)
  }

  const handleSaveSettings = async (payload: any) => {
    if (!project) return
    try {
      const existing = project.plan_items.find((i) => i.type_id === payload.type_id)
      if (existing) {
        await updatePlanItem(project.id, existing.id, payload)
      } else {
        await createPlanItem(project.id, payload)
      }
      await refreshProject()
      setModalOpen(false)
    } catch (e) { /* 已提示 */ }
  }

  const handleSaveAsTemplate = (payload: {
    type_id: string
    title: string
    personal_settings: Record<string, string>
    common_settings: Record<string, string>
    output_settings: Record<string, any>
    note: string
  }) => {
    setPendingTemplate(payload)
    setSaveTemplateOpen(true)
  }

  const handleSaveTemplate = async (data: { name: string; coverUrl: string | null }) => {
    if (!pendingTemplate || !project) return
    try {
      await createTemplate(data.name, {
        plan_items: [{
          type_id: pendingTemplate.type_id,
          title: pendingTemplate.title,
          personal_settings: pendingTemplate.personal_settings,
          common_settings: pendingTemplate.common_settings,
          output_settings: pendingTemplate.output_settings,
          note: pendingTemplate.note,
          reference_images: [],
        }],
        market_config: project.market_config,
        output_config: project.output_config,
        selling_points: project.selling_points,
      }, data.coverUrl)
      setTemplates(await getTemplates())
      message.success('已保存到模板')
      setPendingTemplate(null)
      setSaveTemplateOpen(false)
      setModalOpen(false)
    } catch (e) { /* 已提示 */ }
  }

  const handleRenameTemplate = async (templateId: number, newName: string) => {
    try {
      await updateTemplate(templateId, { name: newName })
      setTemplates(await getTemplates())
      message.success('模板名称已更新')
    } catch (e) { /* 已提示 */ }
  }

  // ── 删除策划项 ──
  const handleDeleteItem = async (itemId: number) => {
    if (!project) return
    try {
      await deletePlanItem(project.id, itemId)
      await refreshProject()
    } catch (e) { /* 已提示 */ }
  }

  // ── 复制策划项 ──
  const handleCopyItem = async (item: GalleryPlanItem) => {
    if (!project) return
    try {
      await createPlanItem(project.id, {
        type_id: item.type_id,
        output_settings: { ...item.output_settings },
        reference_images: item.reference_images ? [...item.reference_images] : undefined,
      })
      await refreshProject()
      message.success('已复制该类型')
    } catch (e) {
      message.error('复制失败，请重试')
    }
  }

  // ── 生成 ──
  const handleGenerate = async () => {
    if (!project) return
    if (project.images.length === 0) { message.warning('请先上传至少一张产品原图'); return }
    if (project.plan_items.length === 0) { message.warning('请先在 AI 智能策划台选择要生成的类型'); return }
    setGenerating(true)
    try {
      const res = await generate(project.id)
      setResult({
        total_images: res.total_images,
        total_points: res.total_points,
        total_minutes: res.total_minutes,
        records: res.records,
      })
      setRecords(await getMyRecords())
      await refreshProject()
      message.success(`套图生成完成，共 ${res.total_images} 张`)
    } catch (e) { /* 已提示 */ }
    finally { setGenerating(false) }
  }

  // ── 模板 ──
  const handleApplyTemplate = async (templateId: number) => {
    if (!project) return
    try {
      // 直接用 apply 返回的（已写入策划项的）项目更新界面，避免再依赖 getDraft 的时序
      const updated = await applyTemplate(templateId, project.id)
      setProject(updated)
      const added = (updated.plan_items?.length ?? 0) - (project.plan_items?.length ?? 0)
      message.success(added > 0 ? `模板已应用，新增 ${added} 个出图类型` : '模板已应用到当前任务')
    } catch (e) {
      message.error('应用模板失败，请重试')
    }
  }
  const handleDeleteTemplate = async (templateId: number) => {
    try {
      await deleteTemplate(templateId)
      setTemplates(await getTemplates())
      message.success('模板已删除')
    } catch (e) { /* 已提示 */ }
  }

  const filteredShowcases = showcaseCat === '全部'
    ? showcases
    : showcases.filter((s) => s.category === showcaseCat)

  const totalCount = project
    ? project.plan_items.reduce((sum, i) => sum + (Number(i.output_settings?.count) || 1), 0)
    : 0

  if (loading) {
    return (
      <div className="gallery-page">
        <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}>
          <Spin size="large" />
        </div>
      </div>
    )
  }

  return (
    <div className="gallery-page">
      <div className="shell">
        {/* ========== LEFT: Consolidated Config Panel ========== */}
        <aside className="config-panel">
          {/* ① 上传产品图 */}
          <section className="cfg-section">
            <div className="cfg-header">
              <h3><span className="req-star">*</span>上传产品图</h3>
              <button className="help-btn" title="仅支持多视角上传" onClick={() => message.info('请上传同一款产品的不同角度/细节图，以获得最佳出图效果。')}>ⓘ</button>
            </div>
            <div className="seg"><button className="on">本地上传</button><button onClick={() => message.info('图片库功能开发中')}>图片库</button></div>
            <div
              className="dropzone"
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('drag') }}
              onDragLeave={(e) => e.currentTarget.classList.remove('drag')}
              onDrop={(e) => {
                e.preventDefault(); e.currentTarget.classList.remove('drag')
                handleFiles(e.dataTransfer.files)
              }}
            >
              <div className="dz-ico">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 16V4m0 0L8 8m4-4l4 4" /><path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
                </svg>
              </div>
              <h4>拖拽或点击上传</h4>
              <p>支持 JPG / PNG / WEBP，单张 ≤ 10MB</p>
              <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={(e) => handleFiles(e.target.files)} />
            </div>
            {!warnClosed && (
              <div className="warn-banner">
                <span className="wb-icon">⚠️</span>
                <span>注意：请上传<strong>同一款产品的不同角度/细节图</strong>，请勿混传不同类产品，以免 AI 识别混乱。</span>
                <button className="wb-close" onClick={() => setWarnClosed(true)} title="关闭提示">✕</button>
              </div>
            )}
            <div className="thumbs">
              {project?.images.map((img) => (
                <div key={img.id} className={`thumb ${img.original ? 'orig' : ''}`}>
                  <Image src={img.url} alt="" preview={{ mask: false }} />
                  {img.original && <span className="badge-orig">原图</span>}
                  <button className="rm" onClick={() => handleDeleteImage(img.id)}>×</button>
                </div>
              ))}
              <div className="thumb-add" onClick={() => fileRef.current?.click()}>+</div>
            </div>
          </section>

          {/* ② 核心卖点 */}
          <section className="cfg-section">
            <div className="cfg-header">
              <h3>✨ 核心卖点</h3>
              <button className="ai-chip" onClick={() => message.info('在「属性设置」弹窗中可使用 AI 帮写自动生成卖点文案。')}>✨ AI 帮写</button>
            </div>
            <div className="field">
              <Input.TextArea
                className="input"
                rows={4}
                value={project?.selling_points || ''}
                placeholder="请输入产品名称、核心卖点、适用人群、理想场景、具体参数等信息，帮助 AI 理解并生成最佳套图"
                maxLength={500}
                onChange={async (e) => {
                  const v = e.target.value
                  setProject((p) => (p ? { ...p, selling_points: v } : p))
                  if (project) { try { await updateProjectSafe(project.id, { selling_points: v }) } catch {} }
                }}
              />
              <div className="char-count">{project?.selling_points?.length || 0} / 500</div>
            </div>
          </section>

          {/* ③ 市场配置 */}
          <section className="config-section">
            <div className="config-head" onClick={(e) => {
              const grid = (e.currentTarget.nextElementSibling as HTMLElement)
              const hidden = grid.style.display === 'none'
              grid.style.display = hidden ? 'grid' : 'none'
              const tog = e.currentTarget.querySelector('.ch-toggle') as HTMLElement
              if (tog) tog.textContent = hidden ? '˄ 收起' : '˅ 展开'
            }}>
              <span className="ch-ico">⊕</span>
              <span className="ch-title">🌍 市场配置</span>
              <span className="spacer" style={{ flex: 1 }} />
              <button className="btn-airec" onClick={(e) => { e.stopPropagation(); message.info('保存策划类型后可使用「AI 帮填」自动推荐市场配置。') }}>✨ AI 推荐</button>
              <span className="ch-toggle">˄ 收起</span>
            </div>
            <div className="cfg-grid">
              {([
                ['ecommerce_platform', '电商平台', options.market.ecommerce_platform],
                ['target_market', '目标市场', options.market.target_market],
                ['copy_language', '文案语种', options.market.copy_language],
                ['visual_style', '视觉风格', options.market.visual_style],
              ] as [keyof GalleryProject['market_config'], string, string[] | undefined][]).map(([key, label, opts]) => (
                <div className="cfg-field" key={key}>
                  <label>{label}</label>
                  <Select
                    value={project?.market_config?.[key as string] || undefined}
                    placeholder="请选择"
                    style={{ width: '100%' }}
                    options={(opts || []).map((o) => ({ label: o, value: o }))}
                    onChange={async (v) => {
                      if (!project) return
                      const mc = { ...project.market_config, [key]: v }
                      setProject({ ...project, market_config: mc })
                      try { await updateProjectSafe(project.id, { market_config: mc }) } catch {}
                    }}
                  />
                </div>
              ))}
            </div>
          </section>

          {/* ④ 全局输出配置 */}
          <section className="config-section output-config">
            <div className="config-head" onClick={(e) => {
              const grid = (e.currentTarget.nextElementSibling as HTMLElement)
              const hidden = grid.style.display === 'none'
              grid.style.display = hidden ? 'grid' : 'none'
              const tog = e.currentTarget.querySelector('.ch-toggle') as HTMLElement
              if (tog) tog.textContent = hidden ? '˄ 收起' : '˅ 展开'
            }}>
              <span className="ch-ico">≡</span>
              <span className="ch-title">⚙ 全局输出配置</span>
              <span className="spacer" style={{ flex: 1 }} />
              <span className="ch-toggle">˄ 收起</span>
            </div>
            <div className="cfg-grid">
              <div className="cfg-field">
                <label>模型</label>
                <Select
                  value={
                    project?.output_config?.provider_id != null && project?.output_config?.model_name
                      ? `${project.output_config.provider_id}::${project.output_config.model_name}`
                      : '__default__'
                  }
                  style={{ width: '100%' }}
                  options={[
                    { label: '默认（自动选择 AI 提供商默认图片模型）', value: '__default__' },
                    ...imageModels.providers.map((p) => ({
                      label: p.provider_name,
                      options: p.models.map((m) => ({ label: m.model_name, value: `${p.provider_id}::${m.model_name}` })),
                    })),
                  ]}
                  onChange={async (val: string) => {
                    if (!project) return
                    let provider_id: number | null = null
                    let model_name: string | null = null
                    let model_label = '默认图片模型'
                    if (val !== '__default__') {
                      const [pid, mname] = val.split('::')
                      provider_id = Number(pid)
                      model_name = mname
                      const prov = imageModels.providers.find((p) => p.provider_id === provider_id)
                      model_label = prov ? `${prov.provider_name} · ${mname}` : mname
                    }
                    const oc = { ...project.output_config, provider_id, model_name, model_label, model: model_label }
                    setProject({ ...project, output_config: oc })
                    try { await updateProjectSafe(project.id, { output_config: oc }) } catch {}
                  }}
                />
                {imageModels.providers.length === 0 && (
                  <p className="hint" style={{ color: 'var(--g-warn, #E0A106)', marginTop: 6 }}>
                    尚未配置 AI 提供商的图片生成模型，将使用默认模型；若未设置则生成示例图。可在「AI 提供商」中添加图片模型。
                  </p>
                )}
              </div>
              <div className="cfg-field">
                <label>分辨率</label>
                <Select
                  value={project?.output_config?.resolution || '1K'}
                  style={{ width: '100%' }}
                  options={(options.output.resolution || []).map((o: string) => ({ label: o, value: o }))}
                  onChange={async (v) => {
                    if (!project) return
                    const oc = { ...project.output_config, resolution: v }
                    setProject({ ...project, output_config: oc })
                    try { await updateProjectSafe(project.id, { output_config: oc }) } catch {}
                  }}
                />
              </div>
              <div className="cfg-field">
                <label>每个类型出图数</label>
                <div className="cfg-stepper-wrap">
                  <div className="cfg-stepper">
                    <button onClick={async () => changeGlobalCount(project, setProject, updateProjectSafe, -1)}>−</button>
                    <span>{project?.output_config?.count || 1}</span>
                    <button onClick={async () => changeGlobalCount(project, setProject, updateProjectSafe, 1)}>+</button>
                  </div>
                </div>
              </div>
              <div className="cfg-field">
                <label>图片比例</label>
                <Select
                  value={project?.output_config?.ratio || '自适应尺寸'}
                  style={{ width: '100%' }}
                  options={(options.output.ratio || []).map((o: string) => ({ label: o, value: o }))}
                  onChange={async (v) => {
                    if (!project) return
                    const oc = { ...project.output_config, ratio: v }
                    setProject({ ...project, output_config: oc })
                    try { await updateProjectSafe(project.id, { output_config: oc }) } catch {}
                  }}
                />
              </div>
            </div>
          </section>

          {/* ⑤ 出图规划列表 */}
          <section className="plan-section">
            <div className="plan-head">
              <div className="plan-head-left">
                <span className="req-star">*</span>
                出图规划列表
                <span className="plan-count">（已选 <b>{project?.plan_items.length || 0}</b>/50 个）</span>
              </div>
              {project && project.plan_items.length > 0 && (
                <button className="plan-clear" onClick={async () => {
                  for (const it of project.plan_items) { try { await deletePlanItem(project.id, it.id) } catch {} }
                  await refreshProject()
                }}>🗑 清空</button>
              )}
            </div>

            <div className="plan-actions">
              <button className="btn-plan-ai" onClick={openDrawer}>✦ AI智能策划台</button>
              <button className="btn-plan-add" title="添加出图任务" onClick={openDrawer}>+</button>
            </div>

            <div className="plan-body">
              {project && project.plan_items.length > 0 ? (
                <div className="plan-rows">
                  {project.plan_items
                    .slice()
                    .sort((a, b) => a.order - b.order)
                    .map((item, idx) => {
                      const t = types.find((x) => x.id === item.type_id)
                      const isFast = !!t?.fast
                      const isCustom = item.type_id === 'custom'
                      const customName = item.personal_settings?.['任务名称'] || item.note || '自定义子任务'
                      return (
                        <PlanRow
                          key={item.id}
                          index={idx + 1}
                          name={isCustom ? customName : typeTitle(types, item.type_id)}
                          fast={isFast}
                          count={Number(item.output_settings?.count) || 1}
                          ratio={item.output_settings?.ratio || (isFast ? '自动' : '3:4')}
                          resolution={item.output_settings?.resolution || '1K'}
                          onCopy={() => handleCopyItem(item)}
                          onDelete={() => handleDeleteItem(item.id)}
                          onSettings={isCustom ? undefined : () => openSettings(item.type_id)}
                        />
                      )
                    })}
                </div>
              ) : (
                <div className="plan-empty">
                  <div className="pe-ico">
                    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <rect x="3" y="3" width="18" height="18" rx="3" /><path d="M3 15l5-5 4 4 3-3 6 6" /><circle cx="9" cy="9" r="1.6" />
                    </svg>
                  </div>
                  <h4>暂无出图规划</h4>
                  <p>点击上方「✦ AI 智能策划台」选择出图类型，或用「⚡ 极速添加」一键生成</p>
                </div>
              )}
            </div>

            <div className="plan-usage">
              <div className="pu-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4m0-4h.01"/></svg>
                使用说明
              </div>
              <ul className="pu-list">
                <li data-n="1.">支持多角度组图上传，AI 能更精准还原产品结构。</li>
                <li data-n="2.">请在全局设置中选择目标市场，AI 将自动调整模特人与场景风格。</li>
                <li data-n="3.">智能模式下，AI 会自动规划整套详情页所需的图片组合。</li>
                <li data-n="4.">新手引导：<button className="pu-link" onClick={() => message.info('新手引导功能开发中')}>查看新手引导</button></li>
              </ul>
            </div>
          </section>

          {/* 生成按钮 */}
          <div className="gen-bar">
            <button className="btn-generate" onClick={handleGenerate} disabled={generating || !project || project.images.length === 0 || project.plan_items.length === 0}>
              ✦ {generating ? '生成中…' : '立即生成'}
              <small>预计生成 {totalCount} 张 · 消耗 {project?.estimated_points || 0} 积分</small>
            </button>
          </div>
        </aside>

        {/* ========== RIGHT: Content Area ========== */}
        <main className="content-area">
          <div className="area-tabs">
            <button className={`area-tab ${areaTab === 'results' ? 'active' : ''}`} onClick={() => setAreaTab('results')}>✦ AI 创作结果</button>
            <button className={`area-tab ${areaTab === 'cases' ? 'active' : ''}`} onClick={() => setAreaTab('cases')}>📋 创作案例</button>
          </div>

          {areaTab === 'results' && (
            <>
              <div className="hero-text">
                <h1>上传产品图，自动生成主图、详情页等整套电商图</h1>
                <p>支持产品多角度，支持智能分析与自定义参数，适配大陆与跨境电商</p>
              </div>

              {/* 完整电商套图 · 示例 */}
              <section className="showcase-section set-feature">
                <div className="showcase-head">
                  <h3>完整电商套图 · 示例</h3>
                  <span className="set-sub">一套标准详情页套图，覆盖从主图到海报的全链路</span>
                </div>
                <div className="set-showcase">
                  <div className="set-hero">
                    <img src="https://picsum.photos/seed/shirt0/600/800" alt="主图" />
                    <span className="set-hero-badge">主图 · 3:4</span>
                  </div>
                  <div className="set-grid">
                    <div className="set-card"><img src="https://picsum.photos/seed/shirt1/400/533" alt="" /><span className="set-card-label">① 产品白底图</span></div>
                    <div className="set-card"><img src="https://picsum.photos/seed/shirt2/400/533" alt="" /><span className="set-card-label">② 场景实拍图</span></div>
                    <div className="set-card"><img src="https://picsum.photos/seed/shirt3/400/533" alt="" /><span className="set-card-label">③ 细节特写图</span></div>
                    <div className="set-card"><img src="https://picsum.photos/seed/shirt4/400/533" alt="" /><span className="set-card-label">④ 核心卖点图</span></div>
                  </div>
                </div>
                <p className="set-note">示例展示 4 / 8 类 · 完整套图还包含：尺寸参数图、包装展示图、使用对比图、活动海报</p>
              </section>

              {/* 热门套图示例 */}
              <section className="showcase-section">
                <div className="showcase-head">
                  <h3>热门套图示例</h3>
                  <div className="showcase-tabs">
                    {(options.showcase_categories || ['全部']).map((c) => (
                      <button key={c} className={`showcase-tab ${showcaseCat === c ? 'on' : ''}`} onClick={() => setShowcaseCat(c)}>{c}</button>
                    ))}
                  </div>
                </div>
                <div className="gallery-grid">
                  {filteredShowcases.map((sc) => {
                    const strip = caseStripImages(sc)
                    return (
                      <article className="case-card" key={sc.id}>
                        <div className="case-strip">
                          <div className="cell orig"><img src={strip[0]} alt="" /><span className="badge-orig">原图</span></div>
                          {strip.slice(1, 3).map((u, i) => (
                            <div className="cell" key={i}><img src={u} alt="" /></div>
                          ))}
                          <div className={`cell ${sc.total_count > 4 ? 'more' : ''}`} data-n={Math.max(0, sc.total_count - 4)}><img src={strip[3] || strip[0]} alt="" /></div>
                        </div>
                        <div className="case-body">
                          <div className="case-meta"><span className="cat-dot" /><span className="cat">{sc.category}</span></div>
                          <p className="case-name">{sc.name}</p>
                          <div className="case-actions">
                            <button className="btn btn-secondary" onClick={() => message.info('已为你打开 AI 智能策划台，可选择类型生成同款。')}>查看详情</button>
                            <button className="btn btn-primary" onClick={openDrawer}>生成同款</button>
                          </div>
                        </div>
                      </article>
                    )
                  })}
                </div>
              </section>

              {/* 创作记录 */}
              {records.length === 0 ? (
                <div className="record-empty">
                  <div className="re-ico">
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <rect x="3" y="3" width="18" height="18" rx="3" /><path d="M3 15l5-5 4 4 3-3 6 6" /><circle cx="9" cy="9" r="1.6" />
                    </svg>
                  </div>
                  <h4>尚无作品，快去创作吧</h4>
                  <p>左侧完成配置后点击「立即生成」即可开始</p>
                </div>
              ) : (
                <section className="showcase-section">
                  <div className="showcase-head"><h3>创作记录</h3></div>
                  <div className="rec-grid">
                    {records.map((r) => (
                      <div className="rec-card" key={r.id}>
                        <img src={r.result_url || ''} alt={r.title} />
                        <div className="rec-cap">{r.title}</div>
                        {r.model_name && <div className="rec-model">🖼 {r.model_name}</div>}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}

          {areaTab === 'cases' && (
            <>
              <div className="hero-text">
                <h1>创作案例库</h1>
                <p>浏览其他用户创作的优秀套图，获取灵感或一键复用</p>
              </div>
              <div className="gallery-grid">
                {showcases.map((sc) => {
                  const strip = caseStripImages(sc)
                  return (
                    <article className="case-card" key={sc.id}>
                      <div className="case-strip">
                        <div className="cell orig"><img src={strip[0]} alt="" /><span className="badge-orig">原图</span></div>
                        {strip.slice(1, 3).map((u, i) => (
                          <div className="cell" key={i}><img src={u} alt="" /></div>
                        ))}
                        <div className={`cell ${sc.total_count > 4 ? 'more' : ''}`} data-n={Math.max(0, sc.total_count - 4)}><img src={strip[3] || strip[0]} alt="" /></div>
                      </div>
                      <div className="case-body">
                        <div className="case-meta"><span className="cat-dot" /><span className="cat">{sc.category}</span></div>
                        <p className="case-name">{sc.name}</p>
                        <div className="case-actions">
                          <button className="btn btn-secondary" onClick={() => message.info('已为你打开 AI 智能策划台，可选择类型生成同款。')}>查看详情</button>
                          <button className="btn btn-primary" onClick={openDrawer}>生成同款</button>
                        </div>
                      </div>
                    </article>
                  )
                })}
              </div>
            </>
          )}
        </main>
      </div>

      {/* 抽屉 + 弹窗 */}
      <PlannerDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        types={types}
        options={options}
        templates={templates}
        imageModels={imageModels}
        initialChecked={project?.plan_items.map((i) => i.type_id) || []}
        onConfirm={confirmDrawer}
        onQuickAdd={quickAddDrawer}
        onApplyTemplate={handleApplyTemplate}
        onDeleteTemplate={handleDeleteTemplate}
        onRenameTemplate={handleRenameTemplate}
        onCreateCustomTask={createCustomTask}
      />
      <TypeSettingsModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        projectId={project?.id || 0}
        type={activeType}
        item={activeItem}
        options={options}
        imageModels={imageModels}
        inheritedModel={
          project?.output_config?.provider_id != null && project?.output_config?.model_name
            ? {
                provider_id: project.output_config.provider_id,
                model_name: project.output_config.model_name,
                model_label: project.output_config.model_label || null,
              }
            : null
        }
        onSave={handleSaveSettings}
        onSaveAsTemplate={handleSaveAsTemplate}
      />

      <SaveTemplateModal
        open={saveTemplateOpen}
        onClose={() => {
          setSaveTemplateOpen(false)
          setPendingTemplate(null)
        }}
        defaultName={pendingTemplate?.title || ''}
        projectImages={project?.images || []}
        onSave={handleSaveTemplate}
      />
      <Modal
        open={!!result}
        onCancel={() => setResult(null)}
        footer={null}
        width={720}
        className="g-modal"
        title="套图生成完成"
      >
        {result && (
          <div>
            <p style={{ color: 'var(--gb-ink-soft)', marginBottom: 16 }}>
              共生成 <b style={{ color: 'var(--gb-brand)' }}>{result.total_images}</b> 张，消耗 {result.total_points} 积分，预计 {result.total_minutes} 分钟。
            </p>
            <div className="result-grid">
              {result.records.map((r) => (
                <img key={r.id} src={r.result_url || ''} alt={r.title} title={r.title} />
              ))}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

// 更新项目（安全版：不抛错，由调用方决定）
async function updateProjectSafe(projectId: number, data: any) {
  return updateProject(projectId, data)
}

async function changeGlobalCount(
  project: GalleryProject | null,
  setProject: (p: GalleryProject | null) => void,
  updateProjectSafe: (id: number, data: any) => Promise<any>,
  delta: number,
) {
  if (!project) return
  const next = Math.max(1, (Number(project.output_config?.count) || 1) + delta)
  const oc = { ...project.output_config, count: next }
  setProject({ ...project, output_config: oc })
  try { await updateProjectSafe(project.id, { output_config: oc }) } catch {}
}
