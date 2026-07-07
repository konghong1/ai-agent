import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ChatSelectorsState {
  providerId: number | null
  providerType: string | null  // 新增: LLM provider type (openai-compatible, qwen, etc.)
  modelName: string | null
  templateId: number | null
  
  setProviderAndModel: (providerId: number, modelName: string | null, providerType?: string | null) => void
  setTemplateId: (templateId: number | null) => void
  clearSelections: () => void
}

export const useChatSelectors = create<ChatSelectorsState>()(
  persist(
    (set) => ({
      providerId: null,
      providerType: null,
      modelName: null,
      templateId: null,
      
      setProviderAndModel: (providerId: number, modelName: string | null, providerType: string | null = null) =>
        set({ providerId, modelName, providerType }),
        
      setTemplateId: (templateId: number | null) => set({ templateId }),
      
      clearSelections: () => set({ providerId: null, providerType: null, modelName: null, templateId: null }),
    }),
    { name: 'chat-selectors' }
  )
)
