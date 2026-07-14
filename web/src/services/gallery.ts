// 电商套图模块 · 前端 API 服务封装
// 所有请求复用 request.ts 的 get/post/patch/del/upload（自动带 token、统一错误处理）。
import { get, post, patch, del, upload } from './request'

const BASE = '/api/gallery'

// ─────────────────────────────────────────────────────────────
// 类型定义（与后端 schemas / gallery_config 对齐）
// ─────────────────────────────────────────────────────────────

export interface GalleryPersonalField {
  label: string
  placeholder?: string
  options?: string[]
}

export interface GalleryType {
  id: string
  title: string
  desc: string
  fast?: boolean
  hasResolution?: boolean
  points?: number
  minutes?: number
  ratioOptions?: string[] | null
  personal: GalleryPersonalField[]
}

export interface GalleryOptions {
  common: Record<string, string[]>
  market: Record<string, string[]>
  output: Record<string, any>
  showcase_categories: string[]
}

export interface GalleryImage {
  id: number
  project_id: number
  filename: string
  url: string
  original: boolean
  order: number
  created_at: string
}

export interface GalleryPlanItem {
  id: number
  project_id: number
  type_id: string
  order: number
  personal_settings: Record<string, string>
  common_settings: Record<string, string>
  output_settings: Record<string, any>
  note: string
  reference_images: string[]
  product_image: string
  status: string
}

export interface GalleryProject {
  id: number
  user_id: number
  name: string
  status: string
  selling_points: string
  market_config: Record<string, string>
  output_config: Record<string, any>
  estimated_points: number
  estimated_minutes: number
  images: GalleryImage[]
  plan_items: GalleryPlanItem[]
  created_at: string
  updated_at: string
}

export interface GalleryRecord {
  id: number
  project_id: number
  plan_item_id: number | null
  type_id: string
  title: string
  result_filename: string | null
  result_url: string | null
  status: string
  error?: string | null
  prompt: string
  prompt_en: string | null
  prompt_source?: string
  // 提示词溯源：喂给 AI 的输入描述 / 模型原始返回（AI 路径才有）
  prompt_input?: string | null
  prompt_raw?: string | null
  provider_id: number | null
  provider_name: string | null
  model_name: string | null
  created_at: string
  task_id?: number | null
  // 生成时刻的 plan_item 配置快照，用于「一键做同款」
  plan_item_snapshot?: {
    type_id: string
    personal_settings: Record<string, string>
    common_settings: Record<string, string>
    output_settings: Record<string, any>
    note: string
    reference_images: string[]
    product_image?: string
  } | null
}

export interface GalleryShowcase {
  id: number
  category: string
  name: string
  original_url: string
  image_urls: string[]
  total_count: number
  // 发布时携带的源任务参数（用于「生成同款」回填）
  payload?: {
    plan_items?: Array<{
      type_id: string
      personal_settings?: Record<string, string>
      common_settings?: Record<string, string>
      output_settings?: Record<string, any>
      note?: string
      reference_images?: string[]
      product_image?: string
    }>
    market_config?: Record<string, string>
    output_config?: Record<string, any>
    selling_points?: string
  } | null
}

export interface GalleryTemplate {
  id: number
  user_id: number
  name: string
  payload: Record<string, any>
  cover_url: string | null
  created_at: string
}

export interface GalleryGenerateResponse {
  project_id: number
  status: string
  total_images: number
  total_points: number
  total_minutes: number
  records: GalleryRecord[]
}

// 一次「立即生成」对应的异步任务，前端据此轮询进度
export interface GalleryTask {
  id: number
  project_id: number
  name: string | null
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial'
  total: number
  done: number
  failed: number
  error: string | null
  created_at: string
  updated_at: string
  records: GalleryRecord[]
}

// ─────────────────────────────────────────────────────────────
// 配置 / 示例
// ─────────────────────────────────────────────────────────────

export function getTypes(): Promise<{ types: GalleryType[]; options: GalleryOptions; features?: { show_prompt?: boolean } }> {
  return get(`${BASE}/types`)
}

export function getShowcases(category?: string): Promise<GalleryShowcase[]> {
  const q = category && category !== '全部' ? `?category=${encodeURIComponent(category)}` : ''
  return get(`${BASE}/showcases${q}`)
}

// 把创作结果里优秀的成图发布到「创作案例」
export interface GalleryShowcaseCreate {
  name: string
  category: string
  record_ids: number[]
}

export function publishShowcase(data: GalleryShowcaseCreate): Promise<GalleryShowcase> {
  return post(`${BASE}/showcases`, data)
}

// ─────────────────────────────────────────────────────────────
// AI 提供商的图片生成模型（动态模型下拉框数据源）
// ─────────────────────────────────────────────────────────────

export interface GalleryImageModelEntry {
  model_id: number
  model_name: string
  is_default: boolean
}

export interface GalleryImageModelProvider {
  provider_id: number
  provider_name: string
  is_default_provider: boolean
  models: GalleryImageModelEntry[]
}

export interface GalleryImageModelsResponse {
  providers: GalleryImageModelProvider[]
  default_image_model: {
    provider_id: number
    provider_name: string
    model_name: string
  } | null
}

export function getImageModels(): Promise<GalleryImageModelsResponse> {
  return get(`${BASE}/image-models`)
}

// ─────────────────────────────────────────────────────────────
// 项目
// ─────────────────────────────────────────────────────────────

export function getDraft(): Promise<GalleryProject> {
  return get(`${BASE}/projects/draft`)
}

export function getProject(projectId: number): Promise<GalleryProject> {
  return get(`${BASE}/projects/${projectId}`)
}

export function updateProject(
  projectId: number,
  data: Partial<Pick<GalleryProject, 'name' | 'selling_points' | 'market_config' | 'output_config' | 'status'>>,
): Promise<GalleryProject> {
  return patch(`${BASE}/projects/${projectId}`, data)
}

// ─────────────────────────────────────────────────────────────
// 产品图
// ─────────────────────────────────────────────────────────────

export function uploadImages(projectId: number, files: File[]): Promise<GalleryProject[]> {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  return upload(`${BASE}/projects/${projectId}/images`, fd)
}

export function deleteImage(projectId: number, imageId: number): Promise<null> {
  return del(`${BASE}/projects/${projectId}/images/${imageId}`)
}

// ─────────────────────────────────────────────────────────────
// 策划项
// ─────────────────────────────────────────────────────────────

export function createPlanItem(
  projectId: number,
  data: {
    type_id: string
    personal_settings?: Record<string, string>
    common_settings?: Record<string, string>
    output_settings?: Record<string, any>
    note?: string
    reference_images?: string[]
    product_image?: string
  },
): Promise<GalleryPlanItem> {
  return post(`${BASE}/projects/${projectId}/plan-items`, data)
}

export function updatePlanItem(
  projectId: number,
  itemId: number,
  data: Partial<{
    type_id: string
    personal_settings: Record<string, string>
    common_settings: Record<string, string>
    output_settings: Record<string, any>
    note: string
    reference_images: string[]
    product_image?: string
    order: number
  }>,
): Promise<GalleryPlanItem> {
  return patch(`${BASE}/projects/${projectId}/plan-items/${itemId}`, data)
}

// 上传策划项「单独商品图」（不写入项目产品图列表），返回 {filename, url}
export function uploadPlanItemImage(
  projectId: number,
  file: File,
): Promise<{ filename: string; url: string }> {
  const fd = new FormData()
  fd.append('file', file)
  return upload(`${BASE}/projects/${projectId}/plan-items/upload-image`, fd)
}

export function deletePlanItem(projectId: number, itemId: number): Promise<null> {
  return del(`${BASE}/projects/${projectId}/plan-items/${itemId}`)
}

export function reorderPlanItems(projectId: number, orderedIds: number[]): Promise<GalleryProject> {
  return post(`${BASE}/projects/${projectId}/plan-items/reorder`, { ordered_ids: orderedIds })
}

// ─────────────────────────────────────────────────────────────
// AI 帮写（由 Agnes 多模态大模型根据产品图生成）
// ─────────────────────────────────────────────────────────────

export function aiFill(
  projectId: number,
  typeId: string,
  current: { personal_settings?: Record<string, string>; common_settings?: Record<string, string>; note?: string },
): Promise<{ common_settings: Record<string, string>; personal_settings: Record<string, string>; note: string }> {
  return post(`${BASE}/projects/${projectId}/ai-fill`, { type_id: typeId, current })
}

// 卖点 AI 帮写：根据产品图，AI 输出结构化卖点
export interface AiSellingPoints {
  product_name: string
  selling_points: string
  audience: string
  scene: string
  params: string
}

export function aiWriteSellingPoints(projectId: number): Promise<AiSellingPoints> {
  return post(`${BASE}/projects/${projectId}/ai-write-selling-points`, {})
}

// ─────────────────────────────────────────────────────────────
// 生成
// ─────────────────────────────────────────────────────────────

export function generate(projectId: number): Promise<GalleryTask> {
  return post(`${BASE}/projects/${projectId}/generate`)
}

// 创作结果：按任务拉取生成进度与已生成的图片
export function getTasks(): Promise<GalleryTask[]> {
  return get(`${BASE}/tasks`)
}

export function getTask(taskId: number): Promise<GalleryTask> {
  return get(`${BASE}/tasks/${taskId}`)
}

export function updateTask(taskId: number, data: { name?: string }): Promise<GalleryTask> {
  return patch(`${BASE}/tasks/${taskId}`, data)
}

export function updateRecord(recordId: number, data: { title?: string }): Promise<GalleryRecord> {
  return patch(`${BASE}/records/${recordId}`, data)
}

export function getProjectRecords(projectId: number): Promise<GalleryRecord[]> {
  return get(`${BASE}/projects/${projectId}/records`)
}

export function getMyRecords(): Promise<GalleryRecord[]> {
  return get(`${BASE}/records`)
}

// ─────────────────────────────────────────────────────────────
// 模板
// ─────────────────────────────────────────────────────────────

export function createTemplate(
  name: string,
  payload: Record<string, any>,
  coverUrl?: string | null,
): Promise<GalleryTemplate> {
  return post(`${BASE}/templates`, { name, payload, cover_url: coverUrl || null })
}

export function getTemplates(): Promise<GalleryTemplate[]> {
  return get(`${BASE}/templates`)
}

export function updateTemplate(
  templateId: number,
  data: { name?: string; coverUrl?: string | null },
): Promise<GalleryTemplate> {
  return patch(`${BASE}/templates/${templateId}`, {
    name: data.name,
    cover_url: data.coverUrl === undefined ? undefined : data.coverUrl || null,
  })
}

export function deleteTemplate(templateId: number): Promise<null> {
  return del(`${BASE}/templates/${templateId}`)
}

export function applyTemplate(templateId: number, projectId: number): Promise<GalleryProject> {
  return post(`${BASE}/templates/${templateId}/apply?project_id=${projectId}`)
}
