import { useEffect, useState } from "react"
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  CloudServerOutlined, StarOutlined,
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
  model_type: "chat" | "embedding"
  enabled: boolean
  is_default_chat: boolean
  is_default_embedding: boolean
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
      message.success(editingProvider ? "更新成功" : "创建成功")
      setProviderModal(false)
      setEditingProvider(null)
      providerForm.resetFields()
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

  const openAddModel = (providerId: number, type: "chat" | "embedding" = "chat") => {
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

  // ---- Render helpers ----

  const renderModelTag = (model: ProviderModel) => {
    const isDefault =
      model.model_type === "chat"
        ? model.is_default_chat
        : model.is_default_embedding
    const star = isDefault ? (
      <StarOutlined style={{ color: "#faad14", marginLeft: 4 }} />
    ) : null

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
          border: "1px solid var(--ice-border)",
          background: model.enabled
            ? "var(--ice-bg-card)"
            : "var(--ice-bg-hover)",
          cursor: "pointer",
          opacity: model.enabled ? 1 : 0.5,
          transition: "all 0.2s",
        }}
        onClick={() => openEditModel(model)}
        onMouseEnter={(e) => {
          ;(e.currentTarget as HTMLElement).style.borderColor =
            "var(--ice-primary)"
        }}
        onMouseLeave={(e) => {
          ;(e.currentTarget as HTMLElement).style.borderColor =
            "var(--ice-border)"
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

  const renderModelsByType = (
    models: ProviderModel[],
    type: "chat" | "embedding"
  ) => {
    const filtered = models.filter((m) => m.model_type === type)
    const label = type === "chat" ? "聊天模型 (Chat)" : "嵌入模型 (Embedding)"

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
            添加{type === "chat" ? "聊天" : "嵌入"}模型
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
                </div>

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


