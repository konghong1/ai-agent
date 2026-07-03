import { useEffect, useState } from 'react'
import { Select } from 'antd'
import { useNavigate } from 'react-router-dom'
import { authHeaders } from '@/services/auth'

// ─── Custom SVG Icons ───────────────────────────────────────────────

/** 星形火花图标 — 代表 AI 模型 */
const ModelIcon = ({ muted = false }: { muted?: boolean }) => (
  <svg
    width="13"
    height="13"
    viewBox="0 0 16 16"
    fill="none"
    style={{ flexShrink: 0, opacity: muted ? 0.4 : 0.8 }}
  >
    <path
      d="M8 2.2L8.8 5.6C8.9 5.95 9.12 6.26 9.42 6.42L12.5 7.5L9.42 8.58C9.12 8.74 8.9 9.05 8.8 9.4L8 12.8L7.2 9.4C7.1 9.05 6.88 8.74 6.58 8.58L3.5 7.5L6.58 6.42C6.88 6.26 7.1 5.95 7.2 5.6L8 2.2Z"
      stroke="currentColor"
      strokeWidth="1.15"
      strokeLinejoin="round"
    />
  </svg>
)

/** 文档图标 — 代表提示词模板 */
const TemplateIcon = ({ muted = false }: { muted?: boolean }) => (
  <svg
    width="13"
    height="13"
    viewBox="0 0 16 16"
    fill="none"
    style={{ flexShrink: 0 }}
  >
    <path
      d="M4.6 1.8H9.4L12.3 4.7V13.5C12.3 13.94 11.97 14.3 11.5 14.3H4.6C4.13 14.3 3.8 13.94 3.8 13.5V2.6C3.8 2.16 4.13 1.8 4.6 1.8Z"
      stroke="currentColor"
      strokeWidth="1.15"
      strokeLinejoin="round"
      opacity={muted ? 0.4 : 0.8}
    />
    <path
      d="M6.5 7.8H10.5M6.5 9.8H10.5M6.5 11.8H9.2"
      stroke="currentColor"
      strokeWidth="1.15"
      strokeLinecap="round"
      opacity={muted ? 0.25 : 0.6}
    />
  </svg>
)

/** 小下拉箭头 */
const ChevronDownIcon = ({ muted = false }: { muted?: boolean }) => (
  <svg
    width="10"
    height="10"
    viewBox="0 0 12 12"
    fill="none"
    style={{ flexShrink: 0, opacity: muted ? 0.3 : 0.6 }}
  >
    <path
      d="M2.5 4.5L6 8L9.5 4.5"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)

// ─── Types ──────────────────────────────────────────────────────────

interface ModelInfo {
  id: number
  name: string
  is_default: boolean
}

interface TypeGroup {
  models: ModelInfo[]
  default: { id: number; name: string } | null
}

interface ProviderData {
  id: number
  name: string
  provider_type: string
  models_by_type: {
    chat: TypeGroup
    video: TypeGroup
    image: TypeGroup
  }
}

interface ChatSelectorProps {
  providerId: number | null
  providerType: string | null
  modelName: string | null
  templateId: number | null
  templates: { id: number; name: string; variables: string[] }[]
  onProviderChange: (providerId: number, modelName: string | null, providerType: string | null) => void
  onTemplateChange: (templateId: number) => void
}

// ─── Constants ──────────────────────────────────────────────────────

const TYPE_LABELS: Record<string, string> = {
  chat: '对话模型',
  video: '视频模型',
  image: '图片模型',
}

const TYPE_COLORS: Record<string, string> = {
  chat: '#2563EB',
  video: '#7C3AED',
  image: '#059669',
}

const TYPE_ORDER = ['chat', 'video', 'image'] as const

// ─── Component ──────────────────────────────────────────────────────

export default function ChatSelector({
  providerId,
  providerType,
  modelName,
  templateId,
  templates,
  onProviderChange,
  onTemplateChange,
}: ChatSelectorProps) {
  const [providers, setProviders] = useState<ProviderData[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/api/providers-chat', { headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) return []
        const data = await r.json()
        return data.providers || []
      })
      .then((list) => {
        setProviders(list)
        // Auto-select default chat model if none selected yet
        if (!providerId) {
          for (const prov of list) {
            const chatGroup = prov.models_by_type?.chat
            if (chatGroup?.default) {
              onProviderChange(prov.id, chatGroup.default.name, prov.provider_type)
              break
            }
          }
        }
      })
      .catch(() => [])
      .finally(() => setLoading(false))
  }, [])

  // ── Build model options grouped by provider → type ──
  const modelOptions = providers.map((provider) => {
    const colorMap = ['#2563EB', '#7C3AED', '#059669', '#D97706', '#DC2626', '#0891B2']
    const colorIndex = provider.id % colorMap.length

    // Provider header label
    const providerLabel = (
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: colorMap[colorIndex],
            flexShrink: 0,
          }}
        />
        <span style={{ fontWeight: 600, color: '#333' }}>{provider.name}</span>
        <span style={{ fontSize: 10, color: '#999' }}>
          {provider.provider_type === 'qwen' ? '通义千问' : provider.provider_type === 'openai-compatible' ? 'OpenAI' : provider.provider_type}
        </span>
      </span>
    )

    // Build model options with type group separators
    const options: any[] = []
    for (const mtype of TYPE_ORDER) {
      const group = provider.models_by_type?.[mtype]
      if (!group || group.models.length === 0) continue

      // Type header (non-selectable separator)
      options.push({
        type: 'type-header',
        label: (
          <span style={{
            display: 'flex', alignItems: 'center', gap: 6, paddingLeft: 4,
            fontSize: 11, color: TYPE_COLORS[mtype], fontWeight: 600,
          }}>
            <span style={{
              display: 'inline-block',
              width: 6, height: 6, borderRadius: 2,
              background: TYPE_COLORS[mtype],
            }} />
            {TYPE_LABELS[mtype]}
            <span style={{ fontWeight: 400, color: '#aaa', fontSize: 10 }}>
              ({group.models.length})
            </span>
          </span>
        ),
        value: `__header__${provider.id}__${mtype}`,
        disabled: true,
      })

      // Model options
      for (const m of group.models) {
        options.push({
          value: `${provider.id}::${m.name}::${provider.provider_type}::${mtype}`,
          label: (
            <span style={{ display: "flex", alignItems: "center", gap: 6, paddingLeft: 10 }}>
              <span>{m.name}</span>
              {m.is_default && (
                <span style={{
                  fontSize: 10, color: "#faad14", fontWeight: 500,
                  background: "rgba(250,173,20,0.1)", padding: "0 4px", borderRadius: 3,
                }}>
                  默认
                </span>
              )}
            </span>
          ),
        })
      }
    }

    return { label: providerLabel, options }
  })

  // ── Parse selection value ──
  const handleModelSelect = (value: string) => {
    const parts = value.split('::')
    if (parts.length < 3) return
    const provId = Number(parts[0])
    const mName = parts[1]
    const pType = parts[2]
    onProviderChange(provId, mName, pType)
  }

  const handleTemplateSelect = (tmplId: number) => {
    onTemplateChange(tmplId)
  }

  // ── Derived state ──
  const currentProviderType = providerType || providers.find((p) => p.id === providerId)?.provider_type
  const modelValue =
    providerId && modelName ? `${providerId}::${modelName}::${currentProviderType || 'openai-compatible'}` : undefined
  const hasModel = !!modelValue
  const hasTemplate = !!templateId

  const tagStyle = (active: boolean) => ({
    display: 'inline-flex' as const,
    alignItems: 'center' as const,
    gap: '4px',
    fontSize: 12,
    color: active ? '#1a1a1a' : '#666',
    cursor: 'pointer',
    transition: 'color 0.15s ease',
  })

  // ── noBorderCss: kill Select border + force text colors ──
  const noBorderCss = `
    .chat-selector-model .ant-select-selector,
    .chat-selector-tmpl .ant-select-selector {
      border: none !important;
      box-shadow: none !important;
      background: transparent !important;
      padding: 0 !important;
      min-height: 0 !important;
      outline: none !important;
    }
    .chat-selector-model.ant-select-focused .ant-select-selector,
    .chat-selector-tmpl.ant-select-focused .ant-select-selector,
    .chat-selector-model:hover .ant-select-selector,
    .chat-selector-tmpl:hover .ant-select-selector {
      border: none !important;
      box-shadow: none !important;
    }
    .chat-selector-model .ant-select-selection-item,
    .chat-selector-tmpl .ant-select-selection-item {
      line-height: 1.4 !important;
      padding: 0 !important;
      color: #1a1a1a !important;
    }
    .chat-selector-model .ant-select-selection-placeholder,
    .chat-selector-tmpl .ant-select-selection-placeholder {
      color: #666 !important;
    }
    /* dropdown panels rendered to body — make sure they aren't clipped */
    .chat-selector-model-dropdown,
    .chat-selector-tmpl-dropdown {
      z-index: 1050 !important;
    }
    /* Style disabled type-header options */
    .chat-selector-model-dropdown .ant-select-item-option-disabled {
      cursor: default !important;
      padding-top: 8px !important;
      padding-bottom: 2px !important;
    }
    .chat-selector-model-dropdown .ant-select-item-option-disabled + .ant-select-item-option {
      padding-top: 2px !important;
    }
  `

  if (loading) return null

  const noProviders = providers.length === 0

  if (noProviders) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 12,
          color: 'var(--ice-text-muted)',
          cursor: 'pointer',
        }}
        onClick={() => navigate('/agents/providers')}
      >
        <ModelIcon muted />
        <span>请先配置 AI 提供商</span>
        <ChevronDownIcon muted />
      </div>
    )
  }

  return (
    <>
      <style>{noBorderCss}</style>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 12,
        }}
      >
        {/* ═══ Model Selector ═══ */}
        <div style={tagStyle(hasModel)}>
          <ModelIcon muted={!hasModel} />
          <Select
            className="chat-selector-model"
            value={modelValue}
            onChange={handleModelSelect as any}
            size="small"
            variant="borderless"
            placeholder="模型"
            options={modelOptions}
            suffixIcon={null}
            getPopupContainer={() => document.body}
            popupClassName="chat-selector-model-dropdown"
            dropdownMatchSelectWidth={false}
            dropdownStyle={{ minWidth: 220 }}
            filterOption={(input: string, option: any) => {
              if (!input || !option?.value) return true
              const val = String(option.value)
              // Allow filtering by model name (skip type headers)
              if (val.startsWith('__header__')) return false
              return val.toLowerCase().includes(input.toLowerCase())
            }}
            labelRender={(props: any) => {
              const val = props.value as string || ''
              const parts = val.split('::')
              const name = parts.length >= 2 ? parts[1] : ''
              if (!name) return <span style={{ color: '#666' }}>模型</span>
              return <span style={{ color: '#1a1a1a' }}>{name}</span>
            }}
          />
          <ChevronDownIcon muted={!hasModel} />
        </div>

        {/* ═══ Template Selector ═══ */}
        <div style={tagStyle(hasTemplate)}>
          <TemplateIcon muted={!hasTemplate} />
          <Select
            className="chat-selector-tmpl"
            value={templateId || undefined}
            onChange={handleTemplateSelect}
            size="small"
            variant="borderless"
            placeholder="模板"
            suffixIcon={null}
            getPopupContainer={() => document.body}
            popupClassName="chat-selector-tmpl-dropdown"
            dropdownMatchSelectWidth={false}
            options={templates.map((t) => ({
              value: t.id,
              label: t.name + (t.variables?.length > 0 ? `  (${t.variables.length} 个变量)` : ''),
            }))}
            optionRender={(opt: any) => (
              <span style={{ fontSize: 13 }}>{opt.label}</span>
            )}
          />
          <ChevronDownIcon muted={!hasTemplate} />
        </div>
      </div>
    </>
  )
}
