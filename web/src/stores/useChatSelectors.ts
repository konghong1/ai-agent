import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// 选中的模型类型：对话 / 视频 / 图片。用于界面参数联动（如"高级参数"面板）。
export type ModelType = 'chat' | 'video' | 'image' | null

interface ChatSelectorsState {
  providerId: number | null
  providerType: string | null  // LLM 提供商类型 (openai-compatible, qwen, ...)
  modelName: string | null
  modelType: ModelType        // 新增：选中的模型类型，用于界面参数联动
  templateId: number | null

  setProviderAndModel: (providerId: number, modelName: string | null, providerType?: string | null, modelType?: ModelType) => void
  setTemplateId: (templateId: number | null) => void
  clearSelections: () => void
}

export const useChatSelectors = create<ChatSelectorsState>()(
  persist(
    (set) => ({
      providerId: null,
      providerType: null,
      modelName: null,
      modelType: null,
      templateId: null,

      setProviderAndModel: (providerId: number, modelName: string | null, providerType: string | null = null, modelType: ModelType = null) =>
        set({ providerId, modelName, providerType, modelType }),

      setTemplateId: (templateId: number | null) => set({ templateId }),

      clearSelections: () => set({ providerId: null, providerType: null, modelName: null, modelType: null, templateId: null }),
    }),
    { name: 'chat-selectors' }
  )
)
