import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Image as AntImage,
  Input,
  Select,
  Button,
  Tag,
  Spin,
  Empty,
  Pagination,
  Card,
  Typography,
  Popconfirm,
  message,
  Checkbox,
  Row,
  Col,
  Statistic,
} from "antd"
import {
  PictureOutlined,
  VideoCameraOutlined,
  DeleteOutlined,
  SearchOutlined,
  ReloadOutlined,
  AppstoreOutlined,
  DownloadOutlined,
} from "@ant-design/icons"
import { get, request } from "@/services/request"
import { proxyMediaUrl } from "@/services/media"

const { Title, Text } = Typography

// ───────────────────────────────────────────────────────────────
// Types
// ───────────────────────────────────────────────────────────────

interface MediaItem {
  id: string
  user_id?: number | null
  username?: string | null
  media_type: "image" | "video" | string
  object_key: string
  proxy_url: string
  mime_type?: string | null
  file_size?: number | null
  status?: string
  created_at?: string | null
  message_id?: number | null
}

interface ListResponse {
  items: MediaItem[]
  total: number
  page: number
  page_size: number
}

interface StatsResponse {
  total: number
  total_bytes: number
  by_type: {
    image: { count: number; bytes: number }
    video: { count: number; bytes: number }
  }
}

// ───────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────

function formatBytes(bytes?: number | null): string {
  if (!bytes) return "0 B"
  const units = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const v = bytes / Math.pow(1024, i)
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function basename(key: string): string {
  const parts = key.split("/")
  return parts[parts.length - 1] || key
}

function formatDate(iso?: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (isNaN(d.getTime())) return "—"
  return d.toLocaleString("zh-CN", { hour12: false })
}

async function downloadFile(url: string) {
  try {
    const res = await fetch(url)
    const blob = await res.blob()
    const a = document.createElement("a")
    a.href = URL.createObjectURL(blob)
    a.download = url.split("/").pop() || "download"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(a.href)
  } catch {
    window.open(url, "_blank")
  }
}

// ───────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────

export default function MediaLibrary() {
  const [items, setItems] = useState<MediaItem[]>([])
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const [mediaType, setMediaType] = useState<string>("all")
  const [query, setQuery] = useState("")
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(24)
  const [total, setTotal] = useState(0)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      })
      if (mediaType !== "all") params.set("media_type", mediaType)
      if (query.trim()) params.set("q", query.trim())

      const [list, stat] = await Promise.all([
        get<ListResponse>(`/api/media/manage/list?${params.toString()}`),
        get<StatsResponse>(`/api/media/manage/stats`),
      ])
      setItems(list.items || [])
      setTotal(list.total || 0)
      setStats(stat)
    } catch {
      // request() already surfaces errors via antd message
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, mediaType, query])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const allSelected = items.length > 0 && items.every((i) => selected.has(i.id))
  const toggleSelectAll = useCallback(() => {
    setSelected((prev) =>
      items.length > 0 && items.every((i) => prev.has(i.id))
        ? new Set()
        : new Set(items.map((i) => i.id)),
    )
  }, [items])

  const handleDeleteOne = useCallback(
    async (id: string) => {
      try {
        await request(`/api/media/manage/${id}`, { method: "DELETE" })
        message.success("已删除")
        setSelected((prev) => {
          const next = new Set(prev)
          next.delete(id)
          return next
        })
        fetchData()
      } catch {
        /* error surfaced by request() */
      }
    },
    [fetchData],
  )

  const handleBulkDelete = useCallback(async () => {
    if (selected.size === 0) return
    setBulkDeleting(true)
    try {
      const ids = Array.from(selected)
      await request("/api/media/manage/bulk", {
        method: "DELETE",
        body: JSON.stringify({ ids }),
      })
      message.success(`已删除 ${ids.length} 项`)
      setSelected(new Set())
      fetchData()
    } catch {
      /* surfaced by request() */
    } finally {
      setBulkDeleting(false)
    }
  }, [selected, fetchData])

  const handleBulkExport = useCallback(async () => {
    if (selected.size === 0) return
    const targets = items.filter((i) => selected.has(i.id))
    for (let i = 0; i < targets.length; i++) {
      downloadFile(proxyMediaUrl(targets[i].proxy_url))
      if (i < targets.length - 1) await new Promise((r) => setTimeout(r, 400))
    }
    message.success(`已开始导出 ${targets.length} 项`)
  }, [selected, items])

  const statsCards = useMemo(() => {
    if (!stats) return null
    return (
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="媒体总数" value={stats.total} prefix={<AppstoreOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="图片"
              value={stats.by_type.image.count}
              prefix={<PictureOutlined style={{ color: "#059669" }} />}
              valueStyle={{ color: "#059669" }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="视频"
              value={stats.by_type.video.count}
              prefix={<VideoCameraOutlined style={{ color: "#7C3AED" }} />}
              valueStyle={{ color: "#7C3AED" }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="占用空间" value={formatBytes(stats.total_bytes)} />
          </Card>
        </Col>
      </Row>
    )
  }, [stats])

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ flex: "0 0 auto", marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          媒体库
        </Title>
        <Text type="secondary">
          LLM 生成的图片 / 视频统一存储于 MinIO（桶 ai-agent-minio），此处可检索、预览与清理。
        </Text>
      </div>

      {statsCards}

      {/* ── Toolbar ── */}
      <div
        style={{
          flex: "0 0 auto",
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Select
          value={mediaType}
          onChange={(v) => {
            setMediaType(v)
            setPage(1)
          }}
          style={{ width: 130 }}
          options={[
            { value: "all", label: "全部类型" },
            { value: "image", label: "图片" },
            { value: "video", label: "视频" },
          ]}
        />
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索文件名 / MIME"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={() => setPage(1)}
          style={{ width: 240 }}
        />
        <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>
          刷新
        </Button>

        <div style={{ flex: 1 }} />

        <Checkbox checked={allSelected} onChange={toggleSelectAll} disabled={items.length === 0}>
          全选本页
        </Checkbox>
        <Popconfirm
          title={`确认删除选中的 ${selected.size} 项？`}
          description="将从 MinIO 与数据库中永久移除。"
          okText="删除"
          okButtonProps={{ danger: true }}
          cancelText="取消"
          disabled={selected.size === 0}
          onConfirm={handleBulkDelete}
        >
          <Button danger icon={<DeleteOutlined />} disabled={selected.size === 0} loading={bulkDeleting}>
            批量删除 ({selected.size})
          </Button>
        </Popconfirm>
        <Button icon={<DownloadOutlined />} disabled={selected.size === 0} onClick={handleBulkExport}>
          批量导出 ({selected.size})
        </Button>
      </div>

      {/* ── Grid ── */}
      <div style={{ flex: 1, overflowY: "auto", paddingRight: 4 }}>
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 80 }}>
            <Spin size="large" />
          </div>
        ) : items.length === 0 ? (
          <Empty description="暂无媒体资源" style={{ padding: 80 }} />
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: 16,
            }}
          >
            {items.map((item) => {
              const isImage = item.media_type === "image"
              const checked = selected.has(item.id)
              return (
                <Card
                  key={item.id}
                  size="small"
                  styles={{ body: { padding: 0 } }}
                  style={{
                    overflow: "hidden",
                    outline: checked ? "2px solid var(--ice-primary)" : "none",
                    position: "relative",
                  }}
                >
                  {/* selection + delete overlay */}
                  <div style={{ position: "absolute", top: 8, left: 8, zIndex: 2 }}>
                    <Checkbox
                      checked={checked}
                      onChange={() => toggleSelect(item.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </div>
                  <div style={{ position: "absolute", top: 8, right: 8, zIndex: 2 }}>
                    <Popconfirm
                      title="确认删除该项？"
                      okText="删除"
                      okButtonProps={{ danger: true }}
                      cancelText="取消"
                      onConfirm={() => handleDeleteOne(item.id)}
                    >
                      <Button
                        size="small"
                        danger
                        type="text"
                        icon={<DeleteOutlined />}
                        style={{ background: "rgba(0,0,0,0.35)", color: "#fff" }}
                      />
                    </Popconfirm>
                  </div>

                  {/* media preview */}
                  <div
                    style={{
                      height: 150,
                      background: "var(--ice-bg-secondary)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      overflow: "hidden",
                    }}
                  >
                    {isImage ? (
                      <AntImage
                        src={proxyMediaUrl(item.proxy_url)}
                        alt={basename(item.object_key)}
                        style={{ width: "100%", height: 150, objectFit: "cover" }}
                        preview={{ mask: "预览" }}
                      />
                    ) : (
                      <video
                        src={proxyMediaUrl(item.proxy_url)}
                        controls
                        preload="metadata"
                        muted
                        playsInline
                        style={{ width: "100%", height: 150, objectFit: "contain", background: "#000" }}
                      />
                    )}
                  </div>

                  {/* footer */}
                  <div style={{ padding: 10 }}>
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 500,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                      title={basename(item.object_key)}
                    >
                      {basename(item.object_key)}
                    </div>
                    <div style={{ marginTop: 6, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <Tag color={isImage ? "green" : "purple"} style={{ margin: 0 }}>
                        {isImage ? "图片" : "视频"}
                      </Tag>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {formatBytes(item.file_size)}
                      </Text>
                    </div>
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {item.username ? `${item.username} · ` : ""}
                        {formatDate(item.created_at)}
                      </Text>
                    </div>
                  </div>
                </Card>
              )
            })}
          </div>
        )}

        {/* pagination */}
        {total > 0 && (
          <div style={{ display: "flex", justifyContent: "center", padding: "20px 0" }}>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              showSizeChanger
              pageSizeOptions={[12, 24, 48, 96]}
              onChange={(p, ps) => {
                setPage(p)
                setPageSize(ps)
              }}
            />
          </div>
        )}
      </div>
    </div>
  )
}
