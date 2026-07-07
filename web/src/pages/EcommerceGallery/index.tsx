import { useCallback, useEffect, useRef, useState } from 'react'
import { message, Modal, Spin, Input, Select } from 'antd'
import {
  getTypes, getShowcases, getDraft, getMyRecords, getTemplates,
  uploadImages, deleteImage, updateProject,
  createPlanItem, updatePlanItem, deletePlanItem,
  generate, createTemplate, deleteTemplate, applyTemplate,
} from '@/services/gallery'
import type {
  GalleryType, GalleryOptions, GalleryProject, GalleryShowcase,
  GalleryRecord, GalleryTemplate, GalleryPlanItem,
} from '@/services/gallery'
import PlannerDrawer from './PlannerDrawer'
import TypeSettingsModal from './TypeSettingsModal'
import './gallery.css'

function typeTitle(types: GalleryType[], id: string): string {
  return types.find((t) => t.id === id)?.title || id
}

export default function EcommerceGallery() {
  const [types, setTypes] = useState<GalleryType[]>([])
  const [options, setOptions] = useState<GalleryOptions>({ common: {}, market: {}, output: {}, showcase_categories: [] })
  const [project, setProject] = useState<GalleryProject | null>(null)
  const [showcases, setShowcases] = useState<GalleryShowcase[]>([])
  const [showcaseCat, setShowcaseCat] = useState('全部')
  const [records, setRecords] = useState<GalleryRecord[]>([])
  const [templates, setTemplates] = useState<GalleryTemplate[]>([])

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [activeType, setActiveType] = useState<GalleryType | null>(null)
  const [activeItem, setActiveItem] = useState<GalleryPlanItem | undefined>(undefined)

  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<null | {
    total_images: number; total_points: number; total_minutes: number; records: GalleryRecord[]
  }>(null)
  const [loading, setLoading] = useState(true)

  const fileRef = useRef<HTMLInputElement>(null)

  const refreshProject = useCallback(async () => {
    const p = await getDraft()
    setProject(p)
    return p
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [t, p, sc, rec, tpl] = await Promise.all([
        getTypes(), getDraft(), getShowcases(), getMyRecords(), getTemplates(),
      ])
      setTypes(t.types)
      setOptions(t.options)
      setProject(p)
      setShowcases(sc)
      setRecords(rec)
      setTemplates(tpl)
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

  // ── 属性设置弹窗 ──
  const openSettings = (typeId: string) => {
    const t = types.find((x) => x.id === typeId) || null
    const it = project?.plan_items.find((i) => i.type_id === typeId)
    setActiveType(t)
    setActiveItem(it)
    setModalOpen(true)
  }

  const handleSaveSettings = async (payload: any, asTemplate = false) => {
    if (!project) return
    try {
      const existing = project.plan_items.find((i) => i.type_id === payload.type_id)
      if (existing) {
        await updatePlanItem(project.id, existing.id, payload)
      } else {
        await createPlanItem(project.id, payload)
      }
      if (asTemplate) {
        const p = await refreshProject()
        await createTemplate(`套图模板-${new Date().toLocaleDateString()}`, {
          plan_items: (p.plan_items || []).map((i) => ({
            type_id: i.type_id,
            personal_settings: i.personal_settings,
            common_settings: i.common_settings,
            output_settings: i.output_settings,
          })),
          market_config: p.market_config,
          output_config: p.output_config,
          selling_points: p.selling_points,
        })
        setTemplates(await getTemplates())
        message.success('已保存到模板')
      } else {
        await refreshProject()
      }
      setModalOpen(false)
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
      await applyTemplate(templateId, project.id)
      await refreshProject()
      message.success('模板已应用到当前任务')
    } catch (e) { /* 已提示 */ }
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
    return <div style={{ display: 'grid', placeItems: 'center', height: '60vh' }}><Spin size="large" /></div>
  }

  return (
    <div className="gallery-page">
      {/* 页头 */}
      <div className="page-head">
        <div>
          <h1 className="page-title">AI 电商套图生成</h1>
          <p className="page-sub">上传产品多视角图，一键生成主图、详情页、场景图等完整套图</p>
        </div>
        <div className="head-actions">
          <button className="btn-plan-save" onClick={() => message.info('上传产品图与配置后，点击下方「AI 智能策划台」选择出图类型即可开始。')}>使用说明</button>
          <button className="btn-generate" style={{ flexDirection: 'row', gap: 6, padding: '11px 20px' }} onClick={openDrawer}>＋ 新建任务</button>
        </div>
      </div>

      {/* 步骤 1 & 2：上传 + 配置 */}
      <section className="gen-grid">
        <div className="g-panel">
          <h3 className="panel-title"><span className="step">1</span>上传产品图</h3>
          <div className="seg"><button className="on">本地上传</button><button>图片库</button></div>
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
          <div className="upload-note">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--g-brand)" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></svg>
            <span>仅支持多视角上传：请上传同一款产品的<strong>不同角度</strong>照片，出图效果更佳。</span>
          </div>
          <div className="thumbs">
            {project?.images.map((img) => (
              <div key={img.id} className={`thumb ${img.original ? 'orig' : ''}`}>
                <img src={img.url} alt="" />
                {img.original && <span className="badge-orig">原图</span>}
                <button className="rm" onClick={() => handleDeleteImage(img.id)}>×</button>
              </div>
            ))}
            <div className="thumb-add" onClick={() => fileRef.current?.click()}>+</div>
          </div>
        </div>

        <div className="g-panel">
          <h3 className="panel-title"><span className="step">2</span>参数配置</h3>
          <div className="field">
            <label>核心卖点 <button className="ai-chip" onClick={() => message.info('在「属性设置」弹窗中可使用 AI 帮填自动生成卖点文案。')}>✨ AI 帮写</button></label>
            <Input.TextArea
              rows={3}
              value={project?.selling_points || ''}
              placeholder="如：真丝质感、显瘦剪裁、法式复古……"
              onChange={async (e) => {
                const v = e.target.value
                setProject((p) => (p ? { ...p, selling_points: v } : p))
                if (project) { try { await updateProjectSafe(project.id, { selling_points: v }) } catch {} }
              }}
            />
            <p className="hint">一句话讲清产品优势，AI 将据此生成文案与构图建议</p>
          </div>

          <div className="config-section">
            <div className="config-head" onClick={(e) => {
              const grid = (e.currentTarget.nextElementSibling as HTMLElement)
              const hidden = grid.style.display === 'none'
              grid.style.display = hidden ? 'grid' : 'none'
              const tog = e.currentTarget.querySelector('.ch-toggle') as HTMLElement
              if (tog) tog.textContent = hidden ? '︿ 收起' : '﹀ 展开'
            }}>
              <span className="ch-ico">⊕</span>
              <span className="ch-title">市场配置</span>
              <span className="spacer" style={{ flex: 1 }} />
              <button className="btn-airec" onClick={(e) => { e.stopPropagation(); message.info('保存策划类型后可使用「AI 帮填」自动推荐市场配置。') }}>✨ AI帮推荐</button>
              <span className="ch-toggle">︿ 收起</span>
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
          </div>

          <div className="config-section">
            <div className="config-head" onClick={(e) => {
              const grid = (e.currentTarget.nextElementSibling as HTMLElement)
              const hidden = grid.style.display === 'none'
              grid.style.display = hidden ? 'grid' : 'none'
              const tog = e.currentTarget.querySelector('.ch-toggle') as HTMLElement
              if (tog) tog.textContent = hidden ? '︿ 收起' : '﹀ 展开'
            }}>
              <span className="ch-ico">≡</span>
              <span className="ch-title">全局输出配置</span>
              <span className="spacer" style={{ flex: 1 }} />
              <span className="ch-toggle">︿ 收起</span>
            </div>
            <div className="cfg-grid">
              <div className="cfg-field">
                <label>模型</label>
                <Select
                  value={project?.output_config?.model || 'Banana-pro'}
                  style={{ width: '100%' }}
                  options={(options.output.model || []).map((o: string) => ({ label: o, value: o }))}
                  onChange={async (v) => {
                    if (!project) return
                    const oc = { ...project.output_config, model: v }
                    setProject({ ...project, output_config: oc })
                    try { await updateProjectSafe(project.id, { output_config: oc }) } catch {}
                  }}
                />
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
                <div className="g-stepper">
                  <button onClick={async () => changeGlobalCount(project, setProject, updateProjectSafe, -1)}>−</button>
                  <span>{project?.output_config?.count || 1}</span>
                  <button onClick={async () => changeGlobalCount(project, setProject, updateProjectSafe, 1)}>+</button>
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
          </div>
        </div>
      </section>

      {/* 步骤 3：策划台列表 */}
      <section className="g-panel" style={{ marginTop: 20 }}>
        <div className="planner-bar">
          <button className="btn-planner" onClick={openDrawer}>✨ AI智能策划台</button>
          <button className="btn-add-item" title="从推荐类型中选择添加" onClick={openDrawer}>+</button>
        </div>

        <div className={`plan-list ${project && project.plan_items.length ? 'has-items' : 'empty'}`}>
          {project?.plan_items
            .slice()
            .sort((a, b) => a.order - b.order)
            .map((item, idx) => {
              const t = types.find((x) => x.id === item.type_id)
              const isFast = !!t?.fast
              return (
                <div className="plan-row" key={item.id}>
                  <div className="pr-left">
                    <div className="pr-title">
                      <span className="pr-num">{idx + 1}</span>
                      {typeTitle(types, item.type_id)}
                      <span className={`pr-tag ${isFast ? 'fast' : 'custom'}`}>{isFast ? '极速出图' : '自定义'}</span>
                    </div>
                    <div className="pr-meta">
                      <span>数量 {Number(item.output_settings?.count) || 1}</span>
                      <span>|</span>
                      <span>比例 {item.output_settings?.ratio || (isFast ? '自动' : '3:4')}</span>
                      <span>|</span>
                      <span>分辨率 {item.output_settings?.resolution || '1K'}</span>
                    </div>
                  </div>
                  <div className="pr-actions">
                    <button className="pr-action-icon" title="删除" onClick={() => handleDeleteItem(item.id)}>✕</button>
                    <span className="pr-set-link" onClick={() => openSettings(item.type_id)}>设置 ›</span>
                  </div>
                </div>
              )
            })}
        </div>

        {project && project.plan_items.length > 0 && (
          <div className="plan-foot">
            <button className="btn-plan-clear" onClick={async () => {
              for (const it of project.plan_items) { try { await deletePlanItem(project.id, it.id) } catch {} }
              await refreshProject()
            }}>🗑 清空所有类型</button>
            <button className="btn-plan-save" onClick={() => message.info('在类型「属性设置」弹窗中点击「另存为模板」即可保存。')}>另存为模板</button>
          </div>
        )}

        <div className="generate-card">
          <div className="gc-info">
            <h4>立即生成完整套图</h4>
            <p>当前规划 <b>{totalCount}</b> 张，预计 {project?.estimated_minutes || 0} 分钟 · 生成后可一键应用到店铺</p>
          </div>
          <button className="btn-generate" onClick={handleGenerate} disabled={generating || !project || project.images.length === 0 || project.plan_items.length === 0}>
            {generating ? '生成中…' : '立即生成'}
          </button>
        </div>
      </section>

      {/* 热门套图示例 */}
      <h3 className="section-title">
        热门套图示例
        <div className="showcase-tabs">
          {(options.showcase_categories || ['全部']).map((c) => (
            <button key={c} className={`tab ${showcaseCat === c ? 'on' : ''}`} onClick={() => setShowcaseCat(c)}>{c}</button>
          ))}
        </div>
      </h3>
      <div className="case-grid">
        {filteredShowcases.map((sc) => {
          const [orig, ...rest] = sc.image_urls
          const strip = [sc.original_url, ...(rest.length ? rest : [orig, orig, orig])].slice(0, 3)
          return (
            <article className="case" key={sc.id}>
              <div className="case-strip">
                <div className="cell orig"><img src={sc.original_url} alt="" /><span className="badge-orig">原图</span></div>
                {strip.slice(0, 3).map((u, i) => (
                  <div className="cell" key={i}><img src={u} alt="" /></div>
                ))}
                <div className="cell more" data-n={Math.max(0, sc.total_count - 4)} style={{ display: sc.total_count > 4 ? 'grid' : 'none' }}><img src={strip[0]} alt="" /></div>
              </div>
              <div className="case-body">
                <div className="case-meta"><span className="cat-dot" /><span className="cat">{sc.category}</span></div>
                <p className="case-name">{sc.name}</p>
                <div className="case-actions">
                  <button className="btn" onClick={() => message.info('已为你打开 AI 智能策划台，可选择类型生成同款。')}>查看详情</button>
                  <button className="btn primary" onClick={openDrawer}>生成同款</button>
                </div>
              </div>
            </article>
          )
        })}
      </div>

      {/* 创作记录 */}
      <h3 className="section-title">创作记录</h3>
      {records.length === 0 ? (
        <div className="record-empty">
          <div className="re-ico">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="3" y="3" width="18" height="18" rx="3" /><path d="M3 15l5-5 4 4 3-3 6 6" /><circle cx="9" cy="9" r="1.6" />
            </svg>
          </div>
          <h4>创作记录</h4>
          <p>尚无作品，快去生成你的第一套电商套图吧</p>
          <button className="btn btn-primary" onClick={openDrawer} style={{ border: 'none', background: 'var(--g-brand)', color: '#fff', padding: '10px 20px', borderRadius: 10, cursor: 'pointer' }}>＋ 开始创作</button>
        </div>
      ) : (
        <div className="rec-grid">
          {records.map((r) => (
            <div className="rec-card" key={r.id}>
              <img src={r.result_url || ''} alt={r.title} />
              <div className="rec-cap">{r.title}</div>
            </div>
          ))}
        </div>
      )}

      {/* 抽屉 + 弹窗 */}
      <PlannerDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        types={types}
        templates={templates}
        initialChecked={project?.plan_items.map((i) => i.type_id) || []}
        onConfirm={confirmDrawer}
        onApplyTemplate={handleApplyTemplate}
        onDeleteTemplate={handleDeleteTemplate}
      />
      <TypeSettingsModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        projectId={project?.id || 0}
        type={activeType}
        item={activeItem}
        options={options}
        projectImages={project?.images || []}
        onSave={handleSaveSettings}
      />

      {/* 生成结果预览 */}
      <Modal
        open={!!result}
        onCancel={() => setResult(null)}
        footer={null}
        width={720}
        title="套图生成完成"
      >
        {result && (
          <div>
            <p style={{ color: 'var(--ice-text-secondary)', marginBottom: 16 }}>
              共生成 <b style={{ color: 'var(--g-brand)' }}>{result.total_images}</b> 张，消耗 {result.total_points} 积分，预计 {result.total_minutes} 分钟。
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
