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
  prompt: string
  provider_id: number | null
  provider_name: string | null
  model_name: string | null
  created_at: string
}

export interface GalleryShowcase {
  id: number
  category: string
  name: string
  original_url: string
  image_urls: string[]
  total_count: number
}

export interface GalleryTemplate {
  id: number
  user_id: number
  name: string
  payload: Record<string, any>
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

// ─────────────────────────────────────────────────────────────
// 配置 / 示例
// ─────────────────────────────────────────────────────────────

export function getTypes(): Promise<{ types: GalleryType[]; options: GalleryOptions }> {
  return get(`${BASE}/types`)
}

export function getShowcases(category?: string): Promise<GalleryShowcase[]> {
  const q = category && category !== '全部' ? `?category=${encodeURIComponent(category)}` : ''
  return get(`${BASE}/showcases${q}`)
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
    order: number
  }>,
): Promise<GalleryPlanItem> {
  return patch(`${BASE}/projects/${projectId}/plan-items/${itemId}`, data)
}

export function deletePlanItem(projectId: number, itemId: number): Promise<null> {
  return del(`${BASE}/projects/${projectId}/plan-items/${itemId}`)
}

export function reorderPlanItems(projectId: number, orderedIds: number[]): Promise<GalleryProject> {
  return post(`${BASE}/projects/${projectId}/plan-items/reorder`, { ordered_ids: orderedIds })
}

// ─────────────────────────────────────────────────────────────
// AI 帮填（规则化建议）
// ─────────────────────────────────────────────────────────────

export function aiFill(
  projectId: number,
  typeId: string,
  current: { personal_settings?: Record<string, string>; common_settings?: Record<string, string>; note?: string },
): Promise<{ common_settings: Record<string, string>; personal_settings: Record<string, string>; note: string }> {
  return post(`${BASE}/projects/${projectId}/ai-fill`, { type_id: typeId, current })
}

// ─────────────────────────────────────────────────────────────
// 生成
// ─────────────────────────────────────────────────────────────

export function generate(projectId: number): Promise<GalleryGenerateResponse> {
  return post(`${BASE}/projects/${projectId}/generate`)
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

export function createTemplate(name: string, payload: Record<string, any>): Promise<GalleryTemplate> {
  return post(`${BASE}/templates`, { name, payload })
}

export function getTemplates(): Promise<GalleryTemplate[]> {
  return get(`${BASE}/templates`)
}

export function deleteTemplate(templateId: number): Promise<null> {
  return del(`${BASE}/templates/${templateId}`)
}

export function applyTemplate(templateId: number, projectId: number): Promise<GalleryProject> {
  return post(`${BASE}/templates/${templateId}/apply?project_id=${projectId}`)
}
