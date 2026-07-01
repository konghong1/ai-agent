import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ChatSelectorsState {
  providerId: number | null
  modelName: string | null
  templateId: number | null
  setProviderAndModel: (providerId: number, modelName: string | null) => void
  setTemplateId: (templateId: number) => void
  clearSelections: () => void
}

export const useChatSelectors = create<ChatSelectorsState>()(
  persist(
    (set) => ({
      providerId: null,
      modelName: null,
      templateId: null,
      
      setProviderAndModel: (providerId: number, modelName: string | null) =>
        set({ providerId, modelName }),
        
      setTemplateId: (templateId: number) => set({ templateId }),
      
      clearSelections: () => set({ providerId: null, modelName: null, templateId: null }),
    }),
    { name: 'chat-selectors' }
  )
)
