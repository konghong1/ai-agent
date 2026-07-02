import { useEffect, useState } from 'react'
import { Select } from 'antd'
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

interface ProviderData {
  id: number
  name: string
  models: { id: number; name: string; is_default: boolean }[]
  selected_model: { id: number; name: string } | null
}

interface ChatSelectorProps {
  providerId: number | null
  modelName: string | null
  templateId: number | null
  templates: { id: number; name: string; variables: string[] }[]
  onProviderChange: (providerId: number, modelName: string | null) => void
  onTemplateChange: (templateId: number) => void
}

// ─── Component ──────────────────────────────────────────────────────

export default function ChatSelector({
  providerId,
  modelName,
  templateId,
  templates,
  onProviderChange,
  onTemplateChange,
}: ChatSelectorProps) {
  const [providers, setProviders] = useState<ProviderData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/providers-chat', { headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) return []
        const data = await r.json()
        return data.providers || []
      })
      .then(setProviders)
      .catch(() => [])
      .finally(() => setLoading(false))
  }, [])

  // ── Build model options grouped by provider (OptGroup) ──
  const modelOptions = providers.map((provider) => {
    const colorMap = ['#2563EB', '#7C3AED', '#059669', '#D97706', '#DC2626', '#0891B2']
    const colorIndex = provider.id % colorMap.length

    return {
      label: (
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
          <span style={{ fontWeight: 500, color: 'var(--ice-text-secondary)' }}>
            {provider.name}
          </span>
        </span>
      ),
      options: provider.models.map((m) => ({
        value: `${provider.id}::${m.name}`,
        label: m.name,
      })),
    }
  })

  const handleModelSelect = (value: string) => {
    const sep = value.indexOf('::')
    if (sep === -1) return
    const provId = Number(value.slice(0, sep))
    const mName = value.slice(sep + 2)
    onProviderChange(provId, mName)
  }

  const handleTemplateSelect = (tmplId: number) => {
    onTemplateChange(tmplId)
  }

  // ── Derived state ──
  const modelValue =
    providerId && modelName ? `${providerId}::${modelName}` : undefined
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
  `

  if (loading) return null

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
            dropdownStyle={{ minWidth: 210 }}
            optionRender={(opt: any) => (
              <span style={{ fontSize: 13 }}>{opt.label}</span>
            )}
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
