import { useEffect, useState } from "react"
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  CloudServerOutlined, StarOutlined, CloudDownloadOutlined,
} from "@ant-design/icons"
import { IceCrystalCard } from "@/components/IceCrystalCard"
import {
  Typography, Form, Input, Button, Space, Modal, message,
  Tag, Switch, Select, Divider, Badge, Popconfirm, Collapse
} from "antd"
import { authHeaders } from "@/services/auth"

const { Title, Text } = Typography

// ============ Types ============

interface ProviderModel {
  id: number
  provider_id: number
  model_name: string
  model_type: "chat" | "embedding" | "video" | "image"
  enabled: boolean
  is_default_chat: boolean
  is_default_embedding: boolean
  is_default_video: boolean
  is_default_image: boolean
  description: string
  created_at: string
}

interface Provider {
  id: number
  user_id: number
  name: string
  base_url: string
  api_key: string
  provider_type: string
  enabled: boolean
  is_default: boolean
  created_at: string
  updated_at: string
  models: ProviderModel[]
}

interface RemoteModel {
  name: string
  suggested_type: string  // chat | image | video | embedding
}

const TYPE_LABELS: Record<string, string> = {
  "openai-compatible": "OpenAI 兼容",
  "azure": "Azure OpenAI",
  "other": "其他",
}

const TYPE_COLORS: Record<string, string> = {
  "openai-compatible": "blue",
  "azure": "cyan",
  "other": "default",
}

// ============ Component ============

export default function ProviderManagement() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(false)
  const [providerModal, setProviderModal] = useState(false)
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null)
  const [modelModal, setModelModal] = useState(false)
  const [editingModel, setEditingModel] = useState<ProviderModel | null>(null)
  const [currentProviderId, setCurrentProviderId] = useState<number | null>(null)
  const [providerForm] = Form.useForm()
  const [modelForm] = Form.useForm()

  // ── Remote model fetching (scoped per provider) ──
  // ── Remote model fetching (scoped per provider) ──
  const [remoteModels, setRemoteModels] = useState<RemoteModel[]>([])
  const [selectedRemoteModels, setSelectedRemoteModels] = useState<Set<string>>(new Set())
  const [modelTypeMap, setModelTypeMap] = useState<Record<string, string>>({})  // name → type
  const [activeKeys, setActiveKeys] = useState<string[]>([])
  const [fetchingModels, setFetchingModels] = useState<number | null>(null)
  const [remoteModelError, setRemoteModelError] = useState<string | null>(null)
  const [remoteModelsForProvider, setRemoteModelsForProvider] = useState<number | null>(null) // which provider the fetched models belong to

  // ── Remote model fetching inside the Add Provider modal ──
  const [modalRemoteModels, setModalRemoteModels] = useState<RemoteModel[]>([])
  const [modalSelectedModels, setModalSelectedModels] = useState<Set<string>>(new Set())
  const [modalModelTypeMap, setModalModelTypeMap] = useState<Record<string, string>>({})
  const [modalFetchingModels, setModalFetchingModels] = useState(false)
  const [modalRemoteError, setModalRemoteError] = useState<string | null>(null)

  const fetchProviders = async () => {
    try {
      const res = await fetch("/api/providers", { headers: authHeaders() })
      if (!res.ok) { setProviders([]); return }
      const data = await res.json()
      setProviders(Array.isArray(data) ? data : [])
    } catch {
      setProviders([])
    }
  }

  useEffect(() => { fetchProviders() }, [])

  // ---- Provider CRUD ----

  const handleProviderSave = async (values: any) => {
    setLoading(true)
    try {
      const url = editingProvider
        ? `/api/providers/${editingProvider.id}`
        : "/api/providers"
      const method = editingProvider ? "PATCH" : "POST"
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(values),
      })
      if (!res.ok) throw new Error("保存失败")

      // Batch-add selected remote models from the modal
      const providerId = editingProvider ? editingProvider.id : (await res.json() as Provider).id
      const selected = Array.from(modalSelectedModels) as string[]
      if (selected.length > 0) {
        // Auto-default: first model of each type becomes default for that type
        const typeFirst: Record<string, string> = {}
        for (const name of selected) {
          const mtype = modalModelTypeMap[name] || "chat"
          if (!(mtype in typeFirst)) typeFirst[mtype] = name
        }
        let addedCount = 0
        let failedCount = 0
        const failedNames: string[] = []
        for (const name of selected) {
          const mtype = modalModelTypeMap[name] || "chat"
          const isDefaultForType = typeFirst[mtype] === name
          const modelRes = await fetch(`/api/providers/${providerId}/models`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({
              model_name: name,
              model_type: mtype,
              enabled: true,
              is_default_chat: isDefaultForType && mtype === "chat",
              is_default_image: isDefaultForType && mtype === "image",
              is_default_video: isDefaultForType && mtype === "video",
              is_default_embedding: isDefaultForType && mtype === "embedding",
              description: "",
            }),
          })
          if (modelRes.ok) {
            addedCount++
          } else {
            failedCount++
            failedNames.push(name)
          }
        }
        if (failedCount === 0) {
          message.success(editingProvider ? `更新成功，已添加/更新 ${addedCount} 个模型` : `创建成功，已添加 ${addedCount} 个模型`)
        } else if (addedCount > 0) {
          message.warning(`成功 ${addedCount} 个，失败 ${failedCount} 个: ${failedNames.join(", ")}`)
        } else {
          message.error(`全部 ${failedCount} 个模型添加失败`)
        }
      } else {
        message.success(editingProvider ? "更新成功" : "创建成功")
      }

      setProviderModal(false)
      setEditingProvider(null)
      providerForm.resetFields()
      setModalRemoteModels([])
      setModalSelectedModels(new Set())
      setModalModelTypeMap({})
      setModalRemoteError(null)
      fetchProviders()
    } catch (e: any) {
      message.error(e.message || "操作失败")
    } finally {
      setLoading(false)
    }
  }

  const handleProviderDelete = (id: number) => {
    Modal.confirm({
      title: "确认删除",
      content: "删除提供商会同时删除所有关联的模型，此操作不可撤销。",
      okText: "删除",
      okType: "danger",
      onOk: async () => {
        const res = await fetch(`/api/providers/${id}`, {
          method: "DELETE",
          headers: authHeaders(),
        })
        if (res.ok) {
          message.success("已删除")
          fetchProviders()
        }
      },
    })
  }

  // ---- Model CRUD ----

  const openAddModel = (providerId: number, type: "chat" | "embedding" | "video" | "image" = "chat") => {
    setCurrentProviderId(providerId)
    setEditingModel(null)
    modelForm.resetFields()
    modelForm.setFieldsValue({
      provider_id: providerId,
      model_type: type,
      enabled: true,
    })
    setModelModal(true)
  }

  const openEditModel = (model: ProviderModel) => {
    setCurrentProviderId(model.provider_id)
    setEditingModel(model)
    modelForm.setFieldsValue(model)
    setModelModal(true)
  }

  const handleModelSave = async (values: any) => {
    setLoading(true)
    try {
      const url = `/api/providers/${currentProviderId}/models${
        editingModel ? `/${editingModel.id}` : ""
      }`
      const method = editingModel ? "PATCH" : "POST"
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ ...values, provider_id: currentProviderId }),
      })
      if (!res.ok) throw new Error("保存失败")
      message.success(editingModel ? "更新成功" : "添加成功")
      setModelModal(false)
      setEditingModel(null)
      modelForm.resetFields()
      fetchProviders()
    } catch (e: any) {
      message.error(e.message || "操作失败")
    } finally {
      setLoading(false)
    }
  }

  const handleModelDelete = (modelId: number) => {
    Modal.confirm({
      title: "确认删除模型",
      content: "删除后将无法恢复。",
      okText: "删除",
      okType: "danger",
      onOk: async () => {
        const res = await fetch(
          `/api/providers/${currentProviderId}/models/${modelId}`,
          { method: "DELETE", headers: authHeaders() }
        )
        if (res.ok) {
          message.success("已删除")
          fetchProviders()
        }
      },
    })
  }

  // ---- Remote model fetching & batch add ----

  const fetchRemoteModels = async (providerId: number) => {
    setFetchingModels(providerId)
    setRemoteModelError(null)
    setSelectedRemoteModels(new Set())
    setRemoteModelsForProvider(providerId)
    // auto-expand the panel
    setActiveKeys(prev => {
      const key = String(providerId)
      return prev.includes(key) ? prev : [...prev, key]
    })
    try {
      const res = await fetch(`/api/providers/${providerId}/remote-models`, { headers: authHeaders() })
      const data = await res.json()
      if (!res.ok || data.error) {
        setRemoteModelError(data.error || "获取失败")
        setRemoteModels([])
        return
      }
      setRemoteModels(data.models || [])
      // auto-select all by default, init type map
      const entries = (data.models || []) as RemoteModel[]
      setSelectedRemoteModels(new Set(entries.map(m => m.name)))
      const typeMap: Record<string, string> = {}
      entries.forEach(m => { typeMap[m.name] = m.suggested_type || "chat" })
      setModelTypeMap(typeMap)
    } catch (e: any) {
      setRemoteModelError(e.message || "网络错误")
      setRemoteModels([])
    } finally {
      setFetchingModels(null)
    }
  }

  const toggleRemoteModel = (name: string) => {
    setSelectedRemoteModels(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const batchAddModels = async (providerId: number) => {
    const selected = Array.from(selectedRemoteModels)
    if (selected.length === 0) {
      message.warning("请至少选择一个模型")
      return
    }
    setLoading(true)
    try {
      // Auto-default: first model of each type becomes default for that type
      const typeFirst: Record<string, string> = {}
      for (const name of selected) {
        const mtype = modelTypeMap[name] || "chat"
        if (!(mtype in typeFirst)) typeFirst[mtype] = name
      }
      let addedCount = 0
      let failedCount = 0
      const failedNames: string[] = []
      for (const name of selected) {
        const mtype = modelTypeMap[name] || "chat"
        const isDefaultForType = typeFirst[mtype] === name
        const res = await fetch(`/api/providers/${providerId}/models`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            model_name: name,
            model_type: mtype,
            enabled: true,
            is_default_chat: isDefaultForType && mtype === "chat",
            is_default_image: isDefaultForType && mtype === "image",
            is_default_video: isDefaultForType && mtype === "video",
            is_default_embedding: isDefaultForType && mtype === "embedding",
            description: "",
          }),
        })
        if (res.ok) {
          addedCount++
        } else {
          failedCount++
          failedNames.push(name)
        }
      }
      if (failedCount === 0) {
        message.success(`成功添加/更新 ${addedCount} 个模型`)
      } else if (addedCount > 0) {
        message.warning(`成功 ${addedCount} 个，失败 ${failedCount} 个: ${failedNames.join(", ")}`)
      } else {
        message.error(`全部 ${failedCount} 个添加失败`)
      }
      setRemoteModels([])
      setSelectedRemoteModels(new Set())
      setRemoteModelsForProvider(null)
      fetchProviders()
    } catch (e: any) {
      message.error(e.message || "批量添加失败")
    } finally {
      setLoading(false)
    }
  }

  // ── Fetch remote models inside the Add Provider modal ──
  const fetchModalRemoteModels = async () => {
    const values = providerForm.getFieldsValue()
    const base_url = (values.base_url || "").trim()
    const api_key = (values.api_key || "").trim()
    if (!base_url || !api_key) {
      message.warning("请先填写 Base URL 和 API Key")
      return
    }
    setModalFetchingModels(true)
    setModalRemoteError(null)
    setModalRemoteModels([])
    setModalSelectedModels(new Set())
    try {
      const res = await fetch("/api/providers/fetch-remote-models", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ base_url, api_key }),
      })
      const data = await res.json()
      if (!res.ok || data.error) {
        setModalRemoteError(data.error || "获取失败")
        return
      }
      const entries = (data.models || []) as RemoteModel[]
      setModalRemoteModels(entries)
      setModalSelectedModels(new Set(entries.map(m => m.name)))
      const typeMap: Record<string, string> = {}
      entries.forEach(m => { typeMap[m.name] = m.suggested_type || "chat" })
      setModalModelTypeMap(typeMap)
    } catch (e: any) {
      setModalRemoteError(e.message || "网络错误")
    } finally {
      setModalFetchingModels(false)
    }
  }

  const toggleModalRemoteModel = (name: string) => {
    setModalSelectedModels(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const renderModelTag = (model: ProviderModel) => {
    const isDefault =
      model.model_type === "chat"
        ? model.is_default_chat
        : model.model_type === "embedding"
        ? model.is_default_embedding
        : model.model_type === "video"
        ? model.is_default_video
        : model.is_default_image
    const star = isDefault ? (
      <StarOutlined style={{ color: "#faad14", marginLeft: 4, fontSize: 13 }} />
    ) : null

    // 默认模型的高亮样式
    const defaultBorder = "1px solid #faad14"
    const defaultBg = "rgba(250, 173, 20, 0.08)"
    const defaultShadow = "0 0 10px rgba(250, 173, 20, 0.18)"
    const defaultHoverBorder = "1px solid #ffc53d"
    const defaultHoverShadow = "0 0 16px rgba(250, 173, 20, 0.32)"

    return (
      <span
        key={model.id}
        style={{
          display: "inline-flex",
          alignItems: "center",
          padding: "4px 10px",
          marginRight: 6,
          marginBottom: 6,
          borderRadius: 6,
          border: isDefault ? defaultBorder : "1px solid var(--ice-border)",
          background: model.enabled
            ? isDefault
              ? defaultBg
              : "var(--ice-bg-card)"
            : "var(--ice-bg-hover)",
          boxShadow: isDefault ? defaultShadow : "none",
          cursor: "pointer",
          opacity: model.enabled ? 1 : 0.5,
          transition: "all 0.2s",
          fontWeight: isDefault ? 500 : "normal",
        }}
        onClick={() => openEditModel(model)}
        onMouseEnter={(e) => {
          const el = e.currentTarget as HTMLElement
          el.style.borderColor = isDefault ? "#ffc53d" : "var(--ice-primary)"
          if (isDefault) {
            el.style.boxShadow = defaultHoverShadow
          }
        }}
        onMouseLeave={(e) => {
          const el = e.currentTarget as HTMLElement
          el.style.border = isDefault ? defaultBorder : "1px solid var(--ice-border)"
          el.style.borderColor = ""
          if (isDefault) {
            el.style.boxShadow = defaultShadow
          }
        }}
      >
        {model.model_name}
        {star}
        <span
          style={{
            marginLeft: 6,
            cursor: "pointer",
            color: "var(--ice-text-muted)",
            fontSize: 12,
            display: "inline-flex",
            alignItems: "center",
            opacity: 0,
            transition: "opacity 0.2s",
          }}
          onClick={(ev) => {
            ev.stopPropagation()
            handleModelDelete(model.id)
          }}
          onMouseEnter={(e) => {
            ;(e.currentTarget as HTMLElement).style.opacity = "1"
          }}
          onMouseLeave={(e) => {
            ;(e.currentTarget as HTMLElement).style.opacity = "0"
          }}
        >
          ×
        </span>
      </span>
    )
  }

  const MODEL_TYPE_LABELS: Record<string, string> = {
    chat: "聊天模型 (Chat)",
    embedding: "嵌入模型 (Embedding)",
    video: "视频模型 (Video)",
    image: "图片模型 (Image)",
  }

  const renderModelsByType = (
    models: ProviderModel[],
    type: "chat" | "embedding" | "video" | "image"
  ) => {
    const filtered = models.filter((m) => m.model_type === type)
    const label = MODEL_TYPE_LABELS[type] || type

    return (
      <div style={{ marginBottom: 16 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 8,
          }}
        >
          <Text strong style={{ color: "var(--ice-text-primary)", fontSize: 14 }}>
            {label}
          </Text>
          <Button
            type="dashed"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => openAddModel(models[0]?.provider_id || currentProviderId!, type)}
          >
            添加{type === "video" ? "视频" : type === "image" ? "图片" : type === "chat" ? "聊天" : "嵌入"}模型
          </Button>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {filtered.length === 0 ? (
            <Text type="secondary" style={{ fontSize: 13, padding: "8px 0" }}>
              暂无模型，点击上方按钮添加
            </Text>
          ) : (
            filtered.map((m) => renderModelTag(m))
          )}
        </div>
      </div>
    )
  }

  // ---- Provider card content ----

  const getProviderColor = (p: Provider) => {
    if (p.is_default) return "gold"
    return p.enabled ? "green" : "red"
  }

  return (
    <IceCrystalCard hoverEffect="none" animation="fadeInUp" style={{ padding: 24 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 20,
        }}
      >
        <div>
          <Title level={4} style={{ margin: 0, color: "var(--ice-text-primary)" }}>
            AI 提供商
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            管理 AI 模型提供商及其可用模型
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditingProvider(null)
            providerForm.resetFields()
            providerForm.setFieldsValue({ enabled: true, is_default: false })
            setModalRemoteModels([])
            setModalSelectedModels(new Set())
            setModalModelTypeMap({})
            setModalRemoteError(null)
            setProviderModal(true)
          }}
        >
          添加提供商
        </Button>
      </div>

      {providers.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "60px 0",
            color: "var(--ice-text-muted)",
          }}
        >
          <CloudServerOutlined
            style={{ fontSize: 48, opacity: 0.3, marginBottom: 12 }}
          />
          <p style={{ marginTop: 8, color: "var(--ice-text-secondary)" }}>
            暂无提供商，点击"添加提供商"开始配置
          </p>
        </div>
      ) : (
        <Collapse
          bordered={false}
          expandIconPosition="right"
          activeKey={activeKeys}
          onChange={(keys) => setActiveKeys(Array.isArray(keys) ? keys as string[] : [])}
          style={{ background: "transparent" }}
          items={providers.map((p) => ({
            key: String(p.id),
            label: (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  width: "100%",
                  padding: "4px 0",
                }}
              >
                <Space size={12}>
                  <Badge
                    status={p.enabled ? "success" : "error"}
                    size="small"
                  />
                  <Title
                    level={5}
                    style={{ margin: 0, color: "var(--ice-text-primary)" }}
                  >
                    {p.name}
                  </Title>
                  <Tag color={TYPE_COLORS[p.provider_type] || "default"}>
                    {TYPE_LABELS[p.provider_type] || p.provider_type}
                  </Tag>
                  {p.is_default && (
                    <Tag color="gold" icon={<StarOutlined />}>默认</Tag>
                  )}
                </Space>
                <Space>
                  <Button
                    type="text"
                    size="small"
                    icon={<CloudDownloadOutlined />}
                    title="从 API 获取模型列表"
                    loading={fetchingModels === p.id}
                    onClick={(e) => {
                      e.stopPropagation()
                      fetchRemoteModels(p.id)
                    }}
                  />
                  <Button
                    type="text"
                    size="small"
                    icon={<PlusOutlined />}
                    title="添加模型"
                    onClick={(e) => {
                      e.stopPropagation()
                      openAddModel(p.id)
                    }}
                  />
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    title="编辑"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditingProvider(p)
                      providerForm.setFieldsValue(p)
                      setProviderModal(true)
                    }}
                  />
                  <Popconfirm
                    title="确认删除"
                    description="删除提供商会同时删除所有关联的模型"
                    okText="删除"
                    cancelText="取消"
                    okType="danger"
                    onConfirm={(e) => {
                      if (e) handleProviderDelete(p.id)
                    }}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      title="删除"
                      danger
                    />
                  </Popconfirm>
                </Space>
              </div>
            ),
            children: (
              <div style={{ padding: "8px 0" }}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 24,
                  }}
                >
                  <div>
                    {renderModelsByType(p.models, "chat")}
                  </div>
                  <div>
                    {renderModelsByType(p.models, "embedding")}
                  </div>
                  <div>
                    {renderModelsByType(p.models, "video")}
                  </div>
                  <div>
                    {renderModelsByType(p.models, "image")}
                  </div>
                </div>

                {/* ═══ Remote model fetching ═══ */}
                {remoteModelsForProvider === p.id && (
                  <div
                    style={{
                      marginTop: 16,
                      padding: "16px 20px",
                      borderRadius: 10,
                      background: "var(--ice-bg-hover)",
                      border: "1px dashed var(--ice-primary)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                      <Space>
                        <CloudDownloadOutlined style={{ color: "var(--ice-primary)", fontSize: 16 }} />
                        <Text strong style={{ color: "var(--ice-text-primary)", fontSize: 14 }}>
                          从 {p.base_url || "API"} 获取到 {remoteModels.length} 个模型
                        </Text>
                      </Space>
                      <Button
                        size="small"
                        icon={<CloudServerOutlined />}
                        loading={fetchingModels === p.id}
                        onClick={() => fetchRemoteModels(p.id)}
                      >
                        重新获取
                      </Button>
                    </div>

                    {remoteModelError && (
                      <Text type="danger" style={{ fontSize: 13, display: "block", marginBottom: 8 }}>错误: {remoteModelError}</Text>
                    )}

                    {remoteModels.length > 0 && (
                      <>
                        <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 12 }}>
                          <Text style={{ fontSize: 13, color: "var(--ice-text-secondary)" }}>
                            每条模型可单独调类型，或使用下方批量选择：
                          </Text>
                          <Button size="small" onClick={() => {
                            setModelTypeMap(prev => {
                              const next = { ...prev }
                              remoteModels.forEach(m => { next[m.name] = "chat" })
                              return next
                            })
                          }}>全部设为对话</Button>
                          <Button size="small" onClick={() => {
                            setModelTypeMap(prev => {
                              const next = { ...prev }
                              remoteModels.forEach(m => { next[m.name] = m.suggested_type || "chat" })
                              return next
                            })
                          }}>恢复建议类型</Button>
                        </div>
                        <div
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: 8,
                            marginBottom: 12,
                            maxHeight: 300,
                            overflowY: "auto",
                          }}
                        >
                          {remoteModels.map(({ name, suggested_type }) => {
                            const checked = selectedRemoteModels.has(name)
                            const existingModels = p.models.map(m => m.model_name)
                            const alreadyAdded = existingModels.includes(name)
                            const currentType = modelTypeMap[name] || suggested_type || "chat"
                            return (
                              <div
                                key={name}
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: 6,
                                  padding: "3px 8px",
                                  border: `1px solid ${checked ? "#1677ff" : "var(--ice-border)"}`,
                                  borderRadius: 6,
                                  background: alreadyAdded ? "var(--ice-bg-hover)" : (checked ? "rgba(22,119,255,0.06)" : "transparent"),
                                  opacity: alreadyAdded ? 0.5 : 1,
                                }}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  disabled={alreadyAdded}
                                  onChange={() => toggleRemoteModel(name)}
                                  style={{ cursor: alreadyAdded ? "not-allowed" : "pointer" }}
                                />
                                <span style={{
                                  fontSize: 12,
                                  textDecoration: alreadyAdded ? "line-through" : "none",
                                  color: "var(--ice-text-primary)",
                                  minWidth: 60,
                                }}>
                                  {name}
                                </span>
                                <Select
                                  size="small"
                                  value={currentType}
                                  onChange={(val) => setModelTypeMap(prev => ({ ...prev, [name]: val }))}
                                  style={{ width: 85, fontSize: 11 }}
                                  options={[
                                    { value: "chat", label: "💬 对话" },
                                    { value: "image", label: "🖼 图片" },
                                    { value: "video", label: "🎬 视频" },
                                    { value: "embedding", label: "📊 嵌入" },
                                  ]}
                                  dropdownMatchSelectWidth={false}
                                />
                              </div>
                            )
                          })}
                        </div>

                        <div style={{
                          display: "flex",
                          gap: 12,
                          alignItems: "center",
                          flexWrap: "wrap",
                        }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            每种类型第一个选中的模型自动设为该类型的默认
                          </Text>
                          <Button
                            type="primary"
                            size="small"
                            loading={loading}
                            onClick={() => batchAddModels(p.id)}
                          >
                            批量添加 ({selectedRemoteModels.size})
                          </Button>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {remoteModelsForProvider !== p.id && (
                  <div style={{ marginTop: 12 }}>
                    <Button
                      size="small"
                      type="primary"
                      ghost
                      icon={<CloudDownloadOutlined />}
                      loading={fetchingModels === p.id}
                      onClick={() => fetchRemoteModels(p.id)}
                    >
                      从 API 获取模型列表
                    </Button>
                  </div>
                )}

                <Divider style={{ margin: "16px 0 12px" }} />

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr 1fr",
                    gap: 16,
                    fontSize: 13,
                  }}
                >
                  <div>
                    <Text type="secondary">Base URL:</Text>
                    <div style={{ marginTop: 4, color: "var(--ice-text-primary)" }}>
                      {p.base_url || <Text type="secondary">使用默认</Text>}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary">API Key:</Text>
                    <div style={{ marginTop: 4, color: "var(--ice-text-primary)", fontFamily: "monospace" }}>
                      {p.api_key
                        ? p.api_key.slice(0, 8) + "****"
                        : <Text type="secondary">未配置</Text>}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary">状态:</Text>
                    <div style={{ marginTop: 4 }}>
                      <Tag color={getProviderColor(p)}>
                        {p.enabled ? "启用" : "禁用"}
                      </Tag>
                    </div>
                  </div>
                </div>
              </div>
            ),
          }))}
        />
      )}

      {/* Provider Modal */}
      <Modal
        title={editingProvider ? "编辑提供商" : "添加提供商"}
        open={providerModal}
        onCancel={() => {
          setProviderModal(false)
          setEditingProvider(null)
          setModalRemoteModels([])
          setModalSelectedModels(new Set())
          setModalModelTypeMap({})
          setModalRemoteError(null)
        }}
        footer={null}
        width={560}
      >
        <Form
          form={providerForm}
          layout="vertical"
          onFinish={handleProviderSave}
          initialValues={{
            provider_type: "openai-compatible",
            enabled: true,
            is_default: false,
          }}
        >
          <Form.Item
            name="name"
            label="提供商名称"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="例如: OpenAI, SiliconFlow, Azure" />
          </Form.Item>
          <Form.Item name="provider_type" label="API 类型">
            <Select>
              <Select.Option value="openai-compatible">OpenAI 兼容</Select.Option>
              <Select.Option value="azure">Azure OpenAI</Select.Option>
              <Select.Option value="other">其他</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="https://api.openai.com/v1（留空使用默认）" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key">
            <Input.Password placeholder="sk-..." />
          </Form.Item>

          {/* Remote model fetching — available in both add and edit mode */}
          <div style={{ marginBottom: 16 }}>
            <Button
              type="primary"
              ghost
              icon={<CloudDownloadOutlined />}
              loading={modalFetchingModels}
              onClick={fetchModalRemoteModels}
            >
              从 API 获取模型列表
            </Button>
            <Text type="secondary" style={{ marginLeft: 12, fontSize: 13 }}>
              填写 Base URL 和 API Key 后拉取可用模型
            </Text>
          </div>

          {modalRemoteError && (
            <div style={{ marginBottom: 16 }}>
              <Text type="danger" style={{ fontSize: 13 }}>{modalRemoteError}</Text>
            </div>
          )}

          {modalRemoteModels.length > 0 && (
            <Form.Item label="选择要添加的模型（可逐个调整类型）">
              <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 12 }}>
                <Button size="small" onClick={() => {
                  setModalModelTypeMap(prev => {
                    const next = { ...prev }
                    modalRemoteModels.forEach(m => { next[m.name] = "chat" })
                    return next
                  })
                }}>全部设为对话</Button>
                <Button size="small" onClick={() => {
                  setModalModelTypeMap(prev => {
                    const next = { ...prev }
                    modalRemoteModels.forEach(m => { next[m.name] = m.suggested_type || "chat" })
                    return next
                  })
                }}>恢复建议类型</Button>
              </div>
              <div style={{ maxHeight: 250, overflowY: "auto", marginBottom: 12 }}>
                {modalRemoteModels.map(({ name, suggested_type }) => {
                  const checked = modalSelectedModels.has(name)
                  const currentType = modalModelTypeMap[name] || suggested_type || "chat"
                  return (
                    <div
                      key={name}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 8,
                        padding: "5px 10px",
                        marginBottom: 4,
                        border: `1px solid ${checked ? "#1677ff" : "var(--ice-border)"}`,
                        borderRadius: 6,
                        background: checked ? "rgba(22,119,255,0.05)" : "transparent",
                      }}
                    >
                      <label style={{
                        display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
                        flex: 1, fontSize: 13,
                      }}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleModalRemoteModel(name)}
                        />
                        <span>{name}</span>
                        <Tag color={suggested_type === "image" ? "green" : suggested_type === "video" ? "purple" : suggested_type === "embedding" ? "orange" : "blue"} style={{ fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
                          {suggested_type === "image" ? "图片" : suggested_type === "video" ? "视频" : suggested_type === "embedding" ? "嵌入" : "对话"}
                        </Tag>
                      </label>
                      <Select
                        size="small"
                        value={currentType}
                        onChange={(val) => setModalModelTypeMap(prev => ({ ...prev, [name]: val }))}
                        style={{ width: 85, fontSize: 11 }}
                        options={[
                          { value: "chat", label: "💬 对话" },
                          { value: "image", label: "🖼 图片" },
                          { value: "video", label: "🎬 视频" },
                          { value: "embedding", label: "📊 嵌入" },
                        ]}
                      />
                    </div>
                  )
                })}
              </div>
              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  每种类型第一个选中的模型自动设为该类型的默认
                </Text>
              </div>
            </Form.Item>
          )}

          <Form.Item
            name="enabled"
            valuePropName="checked"
            label="启用"
          >
            <Switch checkedChildren="开" unCheckedChildren="关" />
          </Form.Item>
          <Form.Item
            name="is_default"
            valuePropName="checked"
            label="设为默认"
          >
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              style={{ marginRight: 8 }}
            >
              确定
            </Button>
            <Button onClick={() => setProviderModal(false)}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* Model Modal */}
      <Modal
        title={editingModel ? "编辑模型" : "添加模型"}
        open={modelModal}
        onCancel={() => {
          setModelModal(false)
          setEditingModel(null)
        }}
        footer={null}
        width={500}
      >
        <Form
          form={modelForm}
          layout="vertical"
          onFinish={handleModelSave}
          initialValues={{ enabled: true }}
        >
          <Form.Item
            name="model_name"
            label="模型名称"
            rules={[{ required: true, message: "请输入模型名称" }]}
          >
            <Input placeholder="例如: gpt-4o, bge-large-zh" />
          </Form.Item>
          <Form.Item
            name="model_type"
            label="模型类型"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="chat">聊天模型 (Chat)</Select.Option>
              <Select.Option value="embedding">嵌入模型 (Embedding)</Select.Option>
              <Select.Option value="image">图片模型 (Image)</Select.Option>
              <Select.Option value="video">视频模型 (Video)</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="模型描述" />
          </Form.Item>
          <Divider style={{ margin: "8px 0" }}>默认标记</Divider>
          <Form.Item
            name="is_default_chat"
            valuePropName="checked"
            label="设为默认聊天模型"
          >
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
          <Form.Item
            name="is_default_embedding"
            valuePropName="checked"
            label="设为默认嵌入模型"
          >
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
          <Form.Item
            name="is_default_video"
            valuePropName="checked"
            label="设为默认视频模型"
          >
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
          <Form.Item
            name="is_default_image"
            valuePropName="checked"
            label="设为默认图片模型"
          >
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
          <Form.Item
            name="enabled"
            valuePropName="checked"
            label="启用"
          >
            <Switch checkedChildren="开" unCheckedChildren="关" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              style={{ marginRight: 8 }}
            >
              确定
            </Button>
            <Button onClick={() => setModelModal(false)}>取消</Button>
          </Form.Item>
        </Form>
      </Modal>
    </IceCrystalCard>
  )
}


