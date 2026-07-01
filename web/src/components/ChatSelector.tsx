import { useEffect, useState } from 'react'
import { Select, Button, Space } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { authHeaders } from '@/services/auth'

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
  onNewThread: () => void
}

export default function ChatSelector({
  providerId,
  modelName,
  templateId,
  templates,
  onProviderChange,
  onTemplateChange,
  onNewThread,
}: ChatSelectorProps) {
  const [providers, setProviders] = useState<ProviderData[]>([])
  const [loading, setLoading] = useState(false)

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

  const handleProviderSelect = (provId: number, _: any, option: any) => {
    const provider = providers.find((p) => p.id === provId)
    const defaultModelId = provider?.selected_model?.id || provider?.models?.[0]?.id || null
    onProviderChange(provId, defaultModelId)
  }

  const handleModelSelect = (name: string) => {
    onProviderChange(providerId || 0, name)
  }

  const handleTemplateSelect = (tmplId: number) => {
    onTemplateChange(tmplId)
  }

  if (loading) return null

  return (
    <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
      {/* Provider & Model Selector */}
      <Space size={4}>
        <span style={{ fontSize: 11, color: 'var(--ice-text-muted)' }}>模型:</span>
        <Select
          value={providerId}
          onChange={handleProviderSelect}
          style={{ width: 120 }}
          size="small"
          placeholder="选择提供商"
          options={providers.map((p) => ({ value: p.id, label: p.name }))}
        />
        <Select
          value={modelName}
          onChange={handleModelSelect}
          style={{ width: 100 }}
          size="small"
          placeholder="选择模型"
          disabled={!providerId}
          options={
            providers
              .find((p) => p.id === providerId)
              ?.models.map((m) => ({ value: m.name, label: m.name })) || []
          }
        />
      </Space>

      {/* Template Selector */}
      <Space size={4}>
        <span style={{ fontSize: 11, color: 'var(--ice-text-muted)' }}>模板:</span>
        <Select
          value={templateId}
          onChange={handleTemplateSelect}
          style={{ width: 150 }}
          size="small"
          placeholder="选择模板"
          options={templates.map((t) => ({
            value: t.id,
            label: t.name + (t.variables?.length > 0 ? ` (${t.variables.length}变)` : ''),
          }))}
        />
      </Space>

      {/* New Thread Button */}
      <Button
        type="dashed"
        size="small"
        icon={<PlusOutlined />}
        onClick={onNewThread}
        style={{ fontSize: 11, height: 24 }}
      >
        新会话
      </Button>
    </div>
  )
}
