import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react'
import { message, Modal, Spin, Input, Select, Image } from 'antd'
import {
  getTypes, getDraft, getTemplates,
  getImageModels, getTasks, getTask, updateTask, updateRecord, getShowcases, publishShowcase,
  uploadImages, deleteImage, updateProject,
  createPlanItem, updatePlanItem, deletePlanItem,
  generate, createTemplate, deleteTemplate, applyTemplate, updateTemplate,
  aiWriteSellingPoints,
} from '@/services/gallery'
import type {
  GalleryType, GalleryOptions, GalleryProject,
  GalleryRecord, GalleryTemplate, GalleryPlanItem,
  GalleryImageModelsResponse, GalleryTask, GalleryShowcase, AiSellingPoints,
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
  // 接受外链、base64、以及本系统生成的 /api/gallery/files/ 文件（含离线 SVG 占位图）
  if (u.startsWith('http') || u.startsWith('data:') || u.startsWith('/api/gallery/files/')) return true
  return false
}

// 离线 SVG 占位图（data URI，无需网络），用于无真实图的兜底
function placeholderImg(label: string): string {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'><rect width='100%' height='100%' fill='#F0EEE9'/><text x='50%' y='50%' font-family='sans-serif' font-size='15' fill='#908E98' text-anchor='middle' dominant-baseline='middle'>${label}</text></svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

// 把用户选择的图片比例映射为 CSS aspect-ratio 字符串，供详情弹窗按设置比例展示
// 可点击放大 + 可下载的图片组件。
// 真实成图用 antd <Image>（点击原生放大预览）；悬停叠加下载按钮，
// 下载时通过 fetch 取 blob 再触发本地保存，避免跨域导致 a.download 失效。
function PreviewableImage({ src, alt, className }: { src: string; alt?: string; className?: string }) {
  const [hover, setHover] = useState(false)
  const [busy, setBusy] = useState(false)
  const filename = (() => {
    try {
      const u = new URL(src, window.location.origin)
      const p = u.pathname.split('/').pop() || 'image'
      return p.includes('.') ? p : `${p}.png`
    } catch {
      return 'image.png'
    }
  })()
  const handleDownload = async (e: MouseEvent) => {
    e.stopPropagation()
    e.preventDefault()
    setBusy(true)
    try {
      const resp = await fetch(src, { method: 'GET' })
      if (!resp.ok) throw new Error('fetch failed')
      const blob = await resp.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000)
    } catch {
      message.info('下载失败，可右键图片保存')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div
      className={`pv-img ${hover ? 'on' : ''}`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <Image src={src} alt={alt} preview={{ mask: false }} className={className} />
      <button className={`pv-dl ${busy ? 'busy' : ''}`} title="下载图片" onClick={handleDownload}>
        {busy ? (
          <span className="pv-dl-spinner" />
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 3v12m0 0l-4-4m4 4l4-4" /><path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
          </svg>
        )}
      </button>
    </div>
  )
}

// 查看单张图片的生成提示词（中英双语）。入口仅在后端 features.show_prompt 开启、且该图
// 确实带有 prompt 时由调用方渲染（见任务卡片与作品详情）。
function PromptBadge({ prompt, prompt_en, promptSource }: { prompt: string; prompt_en?: string | null; promptSource?: string }) {
  const [open, setOpen] = useState(false)
  const [lang, setLang] = useState<'cn' | 'en'>('cn')
  const [copied, setCopied] = useState(false)
  const isAi = promptSource === 'ai'
  const activePrompt = lang === 'en' && prompt_en ? prompt_en : prompt
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(activePrompt)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      message.info('复制失败，请手动选择文本复制')
    }
  }
  return (
    <>
      <button className="prompt-badge" onClick={() => setOpen(true)} title="查看这张图的生成提示词">
        <svg className="prompt-badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.8 9.2L21 11L13.8 12.8L12 20L10.2 12.8L3 11L10.2 9.2L12 2Z" />
        </svg>
        提示词
        {isAi && <span className="prompt-badge-ai">AI</span>}
      </button>
      <Modal
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width={720}
        className="g-modal prompt-modal"
        title={null}
      >
        <div className="prompt-modal-header">
          <div className="prompt-modal-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L13.8 9.2L21 11L13.8 12.8L12 20L10.2 12.8L3 11L10.2 9.2L12 2Z" />
            </svg>
          </div>
          <div className="prompt-modal-titles">
            <h3>图片生成提示词</h3>
            <p>基于当前配置与核心卖点自动组装 · 中文版展示 / 英文版用于模型生成</p>
          </div>
        </div>
        <div className="prompt-modal-body">
          <div className="prompt-lang-tabs">
            <button
              className={lang === 'cn' ? 'active' : ''}
              onClick={() => setLang('cn')}
              type="button"
            >
              中文版
            </button>
            {prompt_en ? (
              <button
                className={lang === 'en' ? 'active' : ''}
                onClick={() => setLang('en')}
                type="button"
              >
                英文版（生成用）
              </button>
            ) : null}
          </div>
          <div className="prompt-text">{activePrompt}</div>
        </div>
        <div className="prompt-modal-footer">
          <span className="prompt-meta">{activePrompt.length} 字 · 已随生成记录保存</span>
          <button className="prompt-copy-btn" onClick={copy}>
            {copied ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
            )}
            {copied ? '已复制' : `复制${lang === 'en' ? '英文' : '中文'}提示词`}
          </button>
        </div>
      </Modal>
    </>
  )
}

// 把一条创作案例（original + image_urls）拼成 4 格 strip，不足用空串占位
function caseStripImages(sc: GalleryShowcase): string[] {
  const arr = [sc.original_url, ...(sc.image_urls || [])]
  while (arr.length < 4) arr.push('')
  return arr.slice(0, 4)
}

function formatTaskTime(iso: string | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => `${n}`.padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export default function EcommerceGallery() {
  const [types, setTypes] = useState<GalleryType[]>([])
  const [options, setOptions] = useState<GalleryOptions>({ common: {}, market: {}, output: {}, showcase_categories: [] })
  const [features, setFeatures] = useState<{ show_prompt?: boolean }>({})
  const [project, setProject] = useState<GalleryProject | null>(null)
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

  // 创作结果：每次「立即生成」对应一个后台任务，列表按时间倒序
  const [tasks, setTasks] = useState<GalleryTask[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [detailGroup, setDetailGroup] = useState<GalleryRecord[] | null>(null)
  const [loading, setLoading] = useState(true)

  // 创作案例：从创作结果发布上去、对外展示、可制作同款（真实数据，非假样图）
  const [areaTab, setAreaTab] = useState<'results' | 'cases'>('results')
  const [showcases, setShowcases] = useState<GalleryShowcase[]>([])
  const [showcaseCat, setShowcaseCat] = useState<string>('全部')
  const [showcaseDetail, setShowcaseDetail] = useState<GalleryShowcase | null>(null)

  // 发布到创作案例：弹窗状态
  const [publishOpen, setPublishOpen] = useState(false)
  const [publishTask, setPublishTask] = useState<GalleryTask | null>(null)
  const [publishName, setPublishName] = useState('')
  const [publishCat, setPublishCat] = useState('')
  const [publishPicks, setPublishPicks] = useState<number[]>([])

  // 任务重命名
  const [editingTaskId, setEditingTaskId] = useState<number | null>(null)
  const [editingName, setEditingName] = useState('')

  // 单张创作记录（图片）重命名
  const [editingRecordId, setEditingRecordId] = useState<number | null>(null)
  const [editingRecordName, setEditingRecordName] = useState('')

  const [warnClosed, setWarnClosed] = useState(false)

  // 卖点 AI 帮写（加载态）
  const [spFilling, setSpFilling] = useState(false)

  const fileRef = useRef<HTMLInputElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  // 任务轮询用 ref：避免每次轮询都重建定时器
  const tasksRef = useRef<GalleryTask[]>(tasks)

  const refreshProject = useCallback(async () => {
    const p = await getDraft()
    setProject(p)
    return p
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [t, p, tpl, im, sc] = await Promise.all([
        getTypes(), getDraft(), getTemplates(), getImageModels(), getShowcases(),
      ])
      setTypes(t.types)
      setOptions(t.options)
      setFeatures(t.features ?? {})
      setProject(p)
      setTemplates(tpl)
      setImageModels(im)
      setShowcases(sc)
      setTasks(await getTasks())
    } catch (e) {
      /* request 已统一提示 */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  // 每次渲染同步最新任务列表到 ref，供轮询定时器读取（定时器只创建一次）
  tasksRef.current = tasks
  // 后台任务轮询：每 1.5s 拉取进行中任务的最新进度（done/total/records）
  useEffect(() => {
    const timer = setInterval(async () => {
      const active = tasksRef.current.filter((t) => t.status === 'pending' || t.status === 'running')
      if (active.length === 0) return
      const updates = await Promise.all(active.map((t) => getTask(t.id).catch(() => null)))
      const map = new Map<number, GalleryTask>()
      updates.forEach((u) => { if (u) map.set(u.id, u) })
      if (map.size === 0) return
      setTasks((prev) => prev.map((t) => (map.has(t.id) ? map.get(t.id)! : t)))
    }, 1500)
    return () => clearInterval(timer)
  }, [])

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
        product_image: item.product_image || '',
      })
      await refreshProject()
      message.success('已复制该类型')
    } catch (e) {
      message.error('复制失败，请重试')
    }
  }

  // ── 生成：提交到后台任务，立即返回任务卡片，按钮保持可点 ──
  const handleGenerate = async () => {
    if (!project) return
    if (project.images.length === 0) { message.warning('请先上传至少一张产品原图'); return }
    if (project.plan_items.length === 0) { message.warning('请先在 AI 智能策划台选择要生成的类型'); return }
    setSubmitting(true)
    try {
      const task = await generate(project.id)
      setTasks((prev) => [task, ...prev])
      message.success('已提交生成任务，正在后台创作中')
      // 跳转到「创作结果」区域顶部，突出最新任务卡片
      contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      /* 已提示 */
    } finally {
      setSubmitting(false)
    }
  }

  // 任务名显示：未命名（空或「未命名套图」）统一回退为「任务 {id}」序号
  const displayTaskName = (t: GalleryTask): string => {
    const n = (t.name || "").trim()
    return n && n !== "未命名套图" ? n : `任务 ${t.id}`
  }

  // ── 重命名任务 ──
  const startRename = (task: GalleryTask) => {
    setEditingTaskId(task.id)
    setEditingName(displayTaskName(task))
  }
  const submitRename = async (taskId: number) => {
    if (!editingName.trim()) {
      setEditingTaskId(null)
      return
    }
    try {
      const updated = await updateTask(taskId, { name: editingName.trim() })
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)))
      message.success('任务名称已更新')
    } catch (e) { /* 已提示 */ } finally {
      setEditingTaskId(null)
      setEditingName('')
    }
  }

  // ── 重命名单张创作记录（图片标题，如「首屏视觉图 #1」）──
  const startRenameRecord = (rec: GalleryRecord) => {
    setEditingRecordId(rec.id)
    setEditingRecordName(rec.title || '')
  }
  const submitRenameRecord = async (recordId: number) => {
    const name = editingRecordName.trim()
    if (!name) {
      setEditingRecordId(null)
      setEditingRecordName('')
      return
    }
    try {
      const updated = await updateRecord(recordId, { title: name })
      setDetailGroup((prev) =>
        prev ? prev.map((r) => (r.id === recordId ? { ...r, title: updated.title } : r)) : prev,
      )
      message.success('图片名称已更新')
    } catch (e) { /* 已提示 */ } finally {
      setEditingRecordId(null)
      setEditingRecordName('')
    }
  }

  // ── 发布到创作案例：从某次任务里勾选优秀成图发布 ──
  const handleOpenPublish = (task: GalleryTask) => {
    setPublishTask(task)
    setPublishName(`${project?.name || '电商套图'} · 套图`)
    setPublishCat((options.showcase_categories && options.showcase_categories[0]) || '其他')
    // 默认勾选所有真实成图（跳过 SVG 占位/失败图）
    setPublishPicks(
      task.records
        .filter((r) => r.result_url && !r.result_url.endsWith('.svg'))
        .map((r) => r.id),
    )
    setPublishOpen(true)
  }

  const handlePublish = async () => {
    if (!publishTask) return
    if (publishPicks.length === 0) { message.warning('请至少勾选一张要发布的成图'); return }
    try {
      await publishShowcase({ name: publishName, category: publishCat, record_ids: publishPicks })
      setShowcases(await getShowcases())
      setPublishOpen(false)
      setPublishTask(null)
      setPublishPicks([])
      message.success('已发布到创作案例')
      setAreaTab('cases')
      contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) { /* 已提示 */ }
  }

  // ── 一键做同款：把当前详情套图的生成配置回填到左侧 ──
  const handleSameStyle = async () => {
    if (!project || !detailGroup || detailGroup.length === 0) return
    setLoading(true)
    try {
      // 收集所有有快照的 record，并按 type_id 去重（保留同类型最后一条）
      const snapshots = detailGroup
        .map((r) => (r.plan_item_snapshot ? { ...r.plan_item_snapshot } : null))
        .filter(Boolean) as GalleryRecord['plan_item_snapshot'][]

      if (snapshots.length === 0) {
        message.warning('该套图没有保存生成配置，无法做同款')
        setDetailGroup(null)
        return
      }

      const byType = new Map<string, NonNullable<GalleryRecord['plan_item_snapshot']>>()
      snapshots.forEach((s) => {
        if (s) byType.set(s.type_id || 'unknown', s)
      })

      // 1. 把全局输出配置带回：取第一张图快照中的 output_settings
      const first = snapshots[0]
      if (first?.output_settings) {
        const oc = { ...project.output_config, ...first.output_settings }
        await updateProjectSafe(project.id, { output_config: oc })
        setProject((prev) => (prev ? { ...prev, output_config: oc } : prev))
      }

      // 2. 逐个类型：已存在则更新，不存在则创建
      for (const [typeId, snapshot] of byType) {
        if (typeId === 'unknown') continue
        const existing = project.plan_items.find((i) => i.type_id === typeId)
        // 注意：有意不回填 snapshot.product_image —— 它指向「源项目」的落盘文件，
        // 在当前（同款）项目中无法解析。留空可让生成时正确回退到本项目的产品图[0]。
        const payload = {
          personal_settings: snapshot.personal_settings || {},
          common_settings: snapshot.common_settings || {},
          output_settings: snapshot.output_settings || {},
          note: snapshot.note || '',
          reference_images: snapshot.reference_images || [],
        }
        if (existing) {
          await updatePlanItem(project.id, existing.id, payload)
        } else {
          await createPlanItem(project.id, { type_id: typeId, ...payload })
        }
      }

      await refreshProject()
      setDetailGroup(null)
      message.success('同款配置已带入左侧，可直接点击「立即生成」')
    } catch (e) {
      message.error('带入同款配置失败，请重试')
    } finally {
      setLoading(false)
    }
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

  const totalCount = project
    ? project.plan_items.reduce((sum, i) => sum + (Number(i.output_settings?.count) || 1), 0)
    : 0

  // 创作案例：按分类筛选
  const filteredShowcases = showcaseCat === '全部'
    ? showcases
    : showcases.filter((s) => s.category === showcaseCat)

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
              <button
                className="ai-chip"
                disabled={spFilling || !project?.images?.length}
                title={project?.images?.length ? '根据产品图，AI 帮写结构化卖点' : '请先上传产品图'}
                onClick={async () => {
                  if (!project) return
                  setSpFilling(true)
                  try {
                    const sp: AiSellingPoints = await aiWriteSellingPoints(project.id)
                    const parts: string[] = []
                    if (sp.product_name) parts.push(`产品名称：${sp.product_name}`)
                    if (sp.selling_points) parts.push(`核心卖点：${sp.selling_points}`)
                    if (sp.audience) parts.push(`适用人群：${sp.audience}`)
                    if (sp.scene) parts.push(`期望场景：${sp.scene}`)
                    if (sp.params) parts.push(`具体参数：${sp.params}`)
                    const merged = parts.join('\n')
                    if (merged) {
                      setProject((p) => (p ? { ...p, selling_points: merged } : p))
                      try { await updateProjectSafe(project.id, { selling_points: merged }) } catch {}
                      message.success('AI 已根据产品图帮写卖点，可继续微调')
                    } else {
                      message.info('AI 暂未返回内容，请手动填写或重试')
                    }
                  } catch {
                    /* 错误已由 request 统一提示 */
                  } finally {
                    setSpFilling(false)
                  }
                }}
              >
                {spFilling ? 'AI 帮写中…' : '✨ AI 帮写'}
              </button>
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
          <button className="btn-generate" onClick={handleGenerate} disabled={submitting || !project || project.images.length === 0 || project.plan_items.length === 0}>
            ✦ {submitting ? '提交中…' : '立即生成'}
            <small>预计生成 {totalCount} 张</small>
          </button>
          </div>
        </aside>

        {/* ========== RIGHT: Content Area ========== */}
        <main className="content-area" ref={contentRef}>
          <div className="area-tabs">
            <button className={`area-tab ${areaTab === 'results' ? 'active' : ''}`} onClick={() => setAreaTab('results')}>📋 创作结果</button>
            <button className={`area-tab ${areaTab === 'cases' ? 'active' : ''}`} onClick={() => setAreaTab('cases')}>✦ 创作案例</button>
            <span className="area-tab-spacer" />
          </div>

          {areaTab === 'results' && (
            <>
              <div className="results-head">
            <div className="rh-left">
              <h2>创作结果</h2>
              <p>每次「立即生成」都会创建一条后台创作任务，实时显示进度与产出图</p>
            </div>
            <div className="rh-stats">
              <div className="rh-stat"><b>{tasks.reduce((s, t) => s + t.total, 0)}</b><span>计划张数</span></div>
              <div className="rh-stat"><b>{tasks.reduce((s, t) => s + t.done, 0)}</b><span>已完成</span></div>
              <div className="rh-stat"><b>{tasks.filter((t) => t.status === 'pending' || t.status === 'running').length}</b><span>进行中</span></div>
            </div>
          </div>

          {tasks.length === 0 ? (
            <div className="record-empty">
              <div className="re-ico">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <rect x="3" y="3" width="18" height="18" rx="3" /><path d="M3 15l5-5 4 4 3-3 6 6" /><circle cx="9" cy="9" r="1.6" />
                </svg>
              </div>
              <h4>尚无创作任务</h4>
              <p>左侧完成产品图与出图规划后，点击「立即生成」即可开始后台创作</p>
            </div>
          ) : (
            <div className="task-list">
              {tasks.map((task) => {
                const running = task.status === 'pending' || task.status === 'running'
                const pct = task.total > 0 ? Math.round((task.done / task.total) * 100) : (running ? 0 : 100)
                return (
                  <article className={`task-card status-${task.status}`} key={task.id} id={`task-${task.id}`}>
                    <div className="task-head">
                      <div className="task-title">
                        <span className="task-time" title={formatTaskTime(task.created_at)}>{formatTaskTime(task.created_at)}</span>
                        {editingTaskId === task.id ? (
                          <Input
                            className="task-rename-input input"
                            value={editingName}
                            autoFocus
                            maxLength={60}
                            onChange={(e) => setEditingName(e.target.value)}
                            onBlur={() => submitRename(task.id)}
                            onPressEnter={() => submitRename(task.id)}
                            onKeyDown={(e) => { if (e.key === 'Escape') { setEditingTaskId(null); setEditingName('') } }}
                          />
                        ) : (
                          <span className="task-pname" onClick={() => startRename(task)} title="点击重命名">
                            {displayTaskName(task)}
                          </span>
                        )}
                        {editingTaskId !== task.id && (
                          <button className="task-rename-btn" title="重命名任务" onClick={() => startRename(task)}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                            </svg>
                          </button>
                        )}
                      </div>
                      <span className={`ts-badge ts-${task.status}`}>
                        {task.status === 'pending' && '排队中'}
                        {task.status === 'running' && '创作中'}
                        {task.status === 'completed' && '已完成'}
                        {task.status === 'partial' && `部分完成（失败 ${task.failed}）`}
                        {task.status === 'failed' && '失败'}
                      </span>
                    </div>
                    <div className="task-progress">
                      <div className="tp-bar"><div className="tp-fill" style={{ width: `${pct}%` }} /></div>
                      <div className="tp-meta">
                        <span className="tp-count">{task.done} / {task.total} 张</span>
                        {running && <span className="tp-dot">● 后台生成中</span>}
                        {task.status === 'failed' && task.error && <span className="tp-err">⚠ {task.error}</span>}
                      </div>
                    </div>
                    <div className="task-grid">
                      {task.records.map((rec, i) => {
                        const isBusy = rec.status === 'pending' || rec.status === 'processing'
                        const isFailed = rec.status === 'failed'
                        const showReal = rec.status === 'completed' && !!rec.result_url && isRealImage(rec.result_url)
                        return (
                          <div
                            className={`task-cell ${isBusy ? 'is-busy' : ''} ${isFailed ? 'is-failed' : ''}`}
                            key={rec.id ?? i}
                          >
                            {showReal ? (
                              <PreviewableImage src={rec.result_url!} alt={rec.title || ''} className="cell-img" />
                            ) : isBusy ? (
                              <div className="cell-busy">
                                <span className="cell-spinner" />
                                <span className="cell-busy-text">
                                  {rec.status === 'processing' ? `生成中 · 第 ${i + 1} 张` : '排队中'}
                                </span>
                              </div>
                            ) : isFailed ? (
                              <div className="cell-failed">
                                <span className="cell-failed-text">生成失败</span>
                              </div>
                            ) : (
                              <img src={placeholderImg(rec.title || '作品')} alt={rec.title || ''} />
                            )}
                            {rec.title && <div className="cell-caption" title={rec.title}>{rec.title}</div>}
                            {features.show_prompt && rec.prompt && <PromptBadge prompt={rec.prompt} prompt_en={rec.prompt_en} promptSource={rec.prompt_source} />}
                          </div>
                        )
                      })}
                      {Array.from({ length: Math.max(0, task.total - task.records.length) }).map((_, i) => (
                        <div className={`task-cell ${running ? 'skeleton' : ''}`} key={`sk-${i}`} />
                      ))}
                    </div>
                    {task.records.length > 0 && (
                      <div className="task-actions">
                        <button className="btn btn-secondary" onClick={() => setDetailGroup(task.records)}>查看详情</button>
                        <button className="btn btn-primary" onClick={() => setDetailGroup(task.records)}>🎨 一键做同款</button>
                      </div>
                    )}
                    {task.records.some((r) => r.result_url && !r.result_url.endsWith('.svg')) && (
                      <button className="btn btn-publish" onClick={() => handleOpenPublish(task)}>📤 发布到创作案例</button>
                    )}
                  </article>
                )
              })}
            </div>
          )}
          </>
          )}

          {areaTab === 'cases' && (
            <>
              <div className="results-head">
                <div className="rh-left">
                  <h2>创作案例</h2>
                  <p>把创作结果里优秀的套图发布到这里对外展示，其他人可一键制作同款</p>
                </div>
                <div className="rh-stats">
                  <div className="rh-stat"><b>{showcases.length}</b><span>案例数</span></div>
                </div>
              </div>

              <section className="showcase-section">
                <div className="showcase-head">
                  <div className="showcase-tabs">
                    {(options.showcase_categories && options.showcase_categories.length ? ['全部', ...options.showcase_categories] : ['全部']).map((c) => (
                      <button key={c} className={`showcase-tab ${showcaseCat === c ? 'on' : ''}`} onClick={() => setShowcaseCat(c)}>{c}</button>
                    ))}
                  </div>
                </div>
                {filteredShowcases.length === 0 ? (
                  <div className="record-empty">
                    <div className="re-ico">
                      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <rect x="3" y="3" width="18" height="18" rx="3" /><path d="M3 15l5-5 4 4 3-3 6 6" /><circle cx="9" cy="9" r="1.6" />
                      </svg>
                    </div>
                    <h4>暂无创作案例</h4>
                    <p>在「创作结果」里挑出优秀的套图，点击「发布到创作案例」即可展示在这里</p>
                  </div>
                ) : (
                  <div className="gallery-grid">
                    {filteredShowcases.map((sc) => {
                      const strip = caseStripImages(sc)
                      return (
                        <article className="case-card" key={sc.id}>
                          <div className="case-strip">
                            <div className="cell orig"><img src={strip[0] && isRealImage(strip[0]) ? strip[0] : placeholderImg(sc.name)} alt="" /><span className="badge-orig">原图</span></div>
                            {strip.slice(1, 3).map((u, i) => (
                              <div className="cell" key={i}><img src={u && isRealImage(u) ? u : placeholderImg('')} alt="" /></div>
                            ))}
                            <div className={`cell ${sc.total_count > 4 ? 'more' : ''}`} data-n={Math.max(0, sc.total_count - 4)}><img src={strip[3] && isRealImage(strip[3]) ? strip[3] : placeholderImg('')} alt="" /></div>
                          </div>
                          <div className="case-body">
                            <div className="case-meta"><span className="cat-dot" /><span className="cat">{sc.category}</span></div>
                            <p className="case-name">{sc.name}</p>
                            <div className="case-actions">
                              <button className="btn btn-secondary" onClick={() => setShowcaseDetail(sc)}>查看详情</button>
                              <button className="btn btn-primary" onClick={openDrawer}>生成同款</button>
                            </div>
                          </div>
                        </article>
                      )
                    })}
                  </div>
                )}
              </section>
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
        projectImages={project?.images || []}
        inheritedModel={
          project?.output_config?.provider_id != null && project?.output_config?.model_name
            ? {
                provider_id: project.output_config.provider_id,
                model_name: project.output_config.model_name,
                model_label: project.output_config.model_label || null,
              }
            : null
        }
        marketConfig={project?.market_config || {}}
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
        open={!!detailGroup}
        onCancel={() => setDetailGroup(null)}
        footer={null}
        width={1200}
        className="g-modal detail-modal"
        title="生成结果详情"
      >
        {detailGroup && (
          <div className="detail-modal-body">
            <div className="detail-layout">
              <div className="detail-product">
                <div className="detail-img">
                  {project?.images?.[0] ? (
                    <PreviewableImage src={project.images[0].url} alt="产品原图" className="cell-img" />
                  ) : (
                    <img src={placeholderImg('产品原图')} alt="产品原图" />
                  )}
                </div>
                <div className="detail-title">产品原图</div>
              </div>
              <div className="detail-right">
                <div className="detail-grid">
                  {detailGroup.map((r) => (
                    <div className="detail-item" key={r.id}>
                      <div className="detail-img">
                        {r.result_url && isRealImage(r.result_url) ? (
                          <PreviewableImage src={r.result_url} alt={r.title} className="cell-img" />
                        ) : (
                          <img src={placeholderImg(r.title || '作品')} alt={r.title} />
                        )}
                      </div>
                      <div className="detail-title-row">
                        {editingRecordId === r.id ? (
                          <Input
                            className="detail-rename-input input"
                            value={editingRecordName}
                            autoFocus
                            maxLength={200}
                            onChange={(e) => setEditingRecordName(e.target.value)}
                            onBlur={() => submitRenameRecord(r.id)}
                            onPressEnter={() => submitRenameRecord(r.id)}
                            onKeyDown={(e) => { if (e.key === 'Escape') { setEditingRecordId(null); setEditingRecordName('') } }}
                          />
                        ) : (
                          <span className="detail-title" onClick={() => startRenameRecord(r)} title="点击重命名">
                            {r.title}
                          </span>
                        )}
                        {editingRecordId !== r.id && (
                          <button className="detail-rename-btn" title="重命名图片" onClick={() => startRenameRecord(r)}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                            </svg>
                          </button>
                        )}
                        {features.show_prompt && r.prompt && (
                          <span className="detail-prompt-badge">
                            <PromptBadge prompt={r.prompt} prompt_en={r.prompt_en} promptSource={r.prompt_source} />
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="detail-actions">
              <button className="btn btn-primary" onClick={handleSameStyle}>🎨 一键做同款</button>
              <button className="btn btn-secondary" onClick={() => { message.success('分享链接已复制'); navigator.clipboard?.writeText(window.location.href).catch(() => {}); }}>🔗 复制分享链接</button>
            </div>
          </div>
        )}
      </Modal>

      {/* 发布到创作案例 */}
      <Modal
        open={publishOpen}
        onCancel={() => setPublishOpen(false)}
        onOk={handlePublish}
        okText="发布到创作案例"
        cancelText="取消"
        title="发布到创作案例"
        width={680}
        className="g-modal publish-modal"
        styles={{ body: { maxHeight: 'calc(85vh - 140px)', overflowY: 'auto' }, content: { maxHeight: '85vh' } }}
      >
        {publishTask && (
          <div className="publish-modal">
            <div className="pf-field">
              <label>案例标题</label>
              <Input value={publishName} onChange={(e) => setPublishName(e.target.value)} placeholder="给这套图起个名字" />
            </div>
            <div className="pf-field">
              <label>分类</label>
              <Select
                value={publishCat}
                style={{ width: '100%' }}
                options={(options.showcase_categories && options.showcase_categories.length ? options.showcase_categories : ['其他']).map((c) => ({ label: c, value: c }))}
                onChange={(v) => setPublishCat(v)}
              />
            </div>
            <div className="pf-field">
              <label className="pf-hint-label">选择要发布的成图（默认已勾选真实成图，示例占位图不可选）</label>
              <div className="pf-picks">
                {publishTask.records.map((rec) => {
                  const real = !!rec.result_url && !rec.result_url.endsWith('.svg')
                  const checked = publishPicks.includes(rec.id)
                  return (
                    <button
                      type="button"
                      key={rec.id}
                      className={`pf-pick ${checked ? 'on' : ''} ${real ? '' : 'disabled'}`}
                      disabled={!real}
                      onClick={() => {
                        if (!real) return
                        setPublishPicks((prev) => (prev.includes(rec.id) ? prev.filter((x) => x !== rec.id) : [...prev, rec.id]))
                      }}
                    >
                      <img src={real ? rec.result_url! : placeholderImg('示例')} alt={rec.title || ''} />
                      <span className="pf-pick-title">{rec.title}</span>
                      {!real && <span className="pf-pick-flag">示例图</span>}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* 创作案例 · 详情 */}
      <Modal
        open={!!showcaseDetail}
        onCancel={() => setShowcaseDetail(null)}
        footer={null}
        width={1200}
        className="g-modal detail-modal"
        title="创作案例详情"
      >
        {showcaseDetail && (
          <div className="detail-modal-body">
            <div className="detail-layout">
              <div className="detail-product">
                <div className="detail-img">
                  {isRealImage(showcaseDetail.original_url) ? (
                    <PreviewableImage src={showcaseDetail.original_url} alt="原图" className="cell-img" />
                  ) : (
                    <img src={placeholderImg(showcaseDetail.name)} alt="原图" />
                  )}
                </div>
                <div className="detail-title">原图</div>
              </div>
              <div className="detail-right">
                <div className="detail-grid">
                  {showcaseDetail.image_urls.map((u, i) => (
                    <div className="detail-item" key={i}>
                      <div className="detail-img">
                        {isRealImage(u) ? (
                          <PreviewableImage src={u} alt="" className="cell-img" />
                        ) : (
                          <img src={placeholderImg('')} alt="" />
                        )}
                      </div>
                      <div className="detail-title">生成图 #{i + 1}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="detail-actions">
              <button className="btn btn-primary" onClick={() => { setShowcaseDetail(null); openDrawer() }}>🎨 生成同款</button>
              <button className="btn btn-secondary" onClick={() => setShowcaseDetail(null)}>关闭</button>
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
