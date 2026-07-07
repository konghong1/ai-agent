import { useState, useRef, useEffect, useCallback } from "react"
import {
  LoadingOutlined, DownloadOutlined, ExpandOutlined,
  CopyOutlined, CheckOutlined,
  ExclamationCircleOutlined, ReloadOutlined,
} from "@ant-design/icons"
import { message } from "antd"
import { proxyMediaUrl } from "@/services/media"

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

export interface ImageBlock {
  type: "image"
  image_url: string
  images?: { url: string }[]
  provider_id?: number
}

export interface VideoBlock {
  type: "video"
  task_id: string
  status: "processing" | "completed" | "failed" | "queued"
  video_url?: string
  error?: string
  provider_id?: number
  progress?: number  // poll count from SSE, indicates backend is actively checking
}

export interface MediaCardProps {
  /** The image or video block */
  block: ImageBlock | VideoBlock
  /** Primary theme color */
  primaryColor: string
  /** Accent theme color */
  accentColor: string
  /** Whether this media is user-generated (affects background tint) */
  isUserMessage?: boolean
  /** Whether to auto-scroll parent when content loads */
  onContentLoaded?: () => void
  /** Click handler for thumbnail images (index in allImages array) */
  onThumbnailClick?: (index: number) => void
}

// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

function getFilename(url: string): string {
  try {
    const path = new URL(url).pathname
    return path.split("/").pop() || "download"
  } catch {
    return url.split("/").pop() || "download"
  }
}

async function downloadFile(url: string) {
  try {
    const res = await fetch(url)
    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = blobUrl
    a.download = getFilename(url)
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(blobUrl)
  } catch {
    window.open(url, "_blank")
  }
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // fallback
    const ta = document.createElement("textarea")
    ta.value = text
    ta.style.position = "fixed"
    ta.style.opacity = "0"
    document.body.appendChild(ta)
    ta.select()
    document.execCommand("copy")
    document.body.removeChild(ta)
    return true
  }
}

// ═══════════════════════════════════════════════════════════════
// Action Button
// ═══════════════════════════════════════════════════════════════

function ActionBtn({
  icon, label, onClick, primaryColor, danger,
}: {
  icon: React.ReactNode
  label: string
  onClick: (e: React.MouseEvent) => void
  primaryColor: string
  danger?: boolean
}) {
  const [hover, setHover] = useState(false)

  return (
    <span
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        flex: 1,
        textAlign: "center",
        padding: "10px 4px",
        cursor: "pointer",
        fontSize: 12,
        fontWeight: 500,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 5,
        color: hover
          ? danger ? "#EF4444" : primaryColor
          : "var(--ice-text-secondary)",
        background: hover
          ? danger ? "rgba(239,68,68,0.06)" : `${primaryColor}0D`
          : "transparent",
        transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
        userSelect: "none",
      }}
    >
      {icon}
      <span>{label}</span>
    </span>
  )
}

// ═══════════════════════════════════════════════════════════════
// Image Card
// ═══════════════════════════════════════════════════════════════

function ImageCard({
  imageUrl, allImages, primaryColor, accentColor, isUserMessage, onLoad, onThumbnailClick,
}: {
  imageUrl: string
  allImages?: { url: string }[]
  primaryColor: string
  accentColor: string
  isUserMessage: boolean
  onLoad: (url: string) => void
  onThumbnailClick?: (index: number) => void
}) {
  const [loaded, setLoaded] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation()
    const ok = await copyToClipboard(imageUrl)
    if (ok) {
      setCopied(true)
      message.success("链接已复制")
      setTimeout(() => setCopied(false), 2000)
    }
  }, [imageUrl])

  const handleDownload = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    downloadFile(proxyMediaUrl(imageUrl))
  }, [imageUrl])

  const handleImageLoad = useCallback(() => {
    setLoaded(true)
    onLoad(imageUrl)
  }, [imageUrl, onLoad])

  return (
    <div style={{
      marginBottom: 12,
      animation: "mediaCardSlideUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",
    }}>
      {/* ── Card Container ── */}
      <div style={{
        borderRadius: "var(--radius-xl)",
        overflow: "hidden",
        background: isUserMessage
          ? `${primaryColor}08`
          : "var(--ice-bg-secondary)",
        border: "1px solid var(--ice-border)",
        boxShadow: "var(--ice-shadow-sm)",
        transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
      }}
        className="media-image-card"
      >
        {/* ── Image Area ── */}
        <div style={{
          position: "relative",
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: 80,
          background: `linear-gradient(135deg, ${primaryColor}06 0%, ${accentColor}06 100%)`,
          cursor: "zoom-in",
          overflow: "hidden",
        }}>
          {/* Loading skeleton */}
          {!loaded && (
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              flexDirection: "column", gap: 12,
            }}>
              <div style={{
                width: "60%", height: 2,
                borderRadius: 1,
                background: `linear-gradient(90deg, transparent, ${primaryColor}40, transparent)`,
                animation: "shimmer 1.5s infinite",
              }} />
              <LoadingOutlined style={{ fontSize: 24, color: "var(--ice-text-muted)" }} />
            </div>
          )}

          {/* Actual image */}
          <img
            src={proxyMediaUrl(imageUrl)}
            alt="Generated"
            loading="lazy"
            onLoad={handleImageLoad}
            style={{
              maxWidth: "100%",
              maxHeight: 380,
              objectFit: "contain",
              display: "block",
              opacity: loaded ? 1 : 0,
              transition: "opacity 0.5s ease",
              userSelect: "none",
            } as React.CSSProperties}
          />

          {/* Hover overlay — expand hint */}
          {loaded && (
            <div className="media-hover-overlay" style={{
              position: "absolute", inset: 0,
              background: "rgba(0,0,0,0)",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "background 0.3s ease",
              pointerEvents: "none",
            }}>
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "10px 20px",
                borderRadius: 24,
                background: "rgba(0,0,0,0)",
                color: "#fff",
                fontSize: 14,
                fontWeight: 500,
                opacity: 0,
                transform: "translateY(4px)",
                transition: "all 0.3s ease",
              }}>
                <ExpandOutlined />
                点击放大
              </div>
            </div>
          )}
        </div>

        {/* ── Action Bar ── */}
        <div style={{
          display: "flex",
          alignItems: "center",
          borderTop: "1px solid var(--ice-border)",
          background: "var(--ice-bg-card)",
        }}>
          <ActionBtn
            icon={<ExpandOutlined />}
            label="预览"
            primaryColor={primaryColor}
            onClick={(e) => { e.stopPropagation(); /* handled by parent */ }}
          />
          <div style={{ width: 1, alignSelf: "stretch", background: "var(--ice-border)" }} />
          <ActionBtn
            icon={<DownloadOutlined />}
            label="下载"
            primaryColor={primaryColor}
            onClick={handleDownload}
          />
          <div style={{ width: 1, alignSelf: "stretch", background: "var(--ice-border)" }} />
          <ActionBtn
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            label={copied ? "已复制" : "复制链接"}
            primaryColor={primaryColor}
            onClick={handleCopy}
          />
        </div>
      </div>

      {/* ── Multi-image thumbnails ── */}
      {allImages && allImages.length > 1 && (
        <div style={{
          display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap",
        }}>
          {allImages.slice(1).map((img, i) => (
            <div
              key={i}
              onClick={(e) => { e.stopPropagation(); onThumbnailClick?.(i + 1) }}
              style={{
                width: 64, height: 64,
                borderRadius: 10,
                overflow: "hidden",
                cursor: "pointer",
                border: "2px solid transparent",
                transition: "all 0.25s ease",
                animation: `mediaCardSlideUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) ${0.05 * (i + 1)}s both`,
                position: "relative",
              }}
              className="media-thumb"
            >
              <img
                src={proxyMediaUrl(img.url)}
                alt={`Variant ${i + 2}`}
                loading="lazy"
                style={{
                  width: "100%", height: "100%",
                  objectFit: "cover",
                  transition: "transform 0.4s ease",
                }}
              />
              {/* Thumb hover hint */}
              <div className="media-thumb-hint" style={{
                position: "absolute", inset: 0,
                background: "rgba(0,0,0,0)",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "background 0.25s ease",
              }}>
                <ExpandOutlined style={{
                  color: "#fff", fontSize: 16, opacity: 0,
                  transform: "scale(0.5)",
                  transition: "all 0.25s ease",
                }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Video Card
// ═══════════════════════════════════════════════════════════════

function VideoCard({
  block, primaryColor, accentColor, isUserMessage,
}: {
  block: VideoBlock
  primaryColor: string
  accentColor: string
  isUserMessage: boolean
}) {
  const [copied, setCopied] = useState(false)
  const [videoSrc, setVideoSrc] = useState('')  // 懒加载：初始为空，进入视口后才设置
  const containerRef = useRef<HTMLDivElement>(null)

  // IntersectionObserver — 按需加载视频
  useEffect(() => {
    if (!block.video_url) return
    // 如果已经有 src 了，不需要再观察
    if (videoSrc) return

    const el = containerRef.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVideoSrc(proxyMediaUrl(block.video_url))
          observer.disconnect()
        }
      },
      { rootMargin: '300px' },  // 提前 300px 开始加载，平衡流畅度和性能
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [block.video_url, videoSrc])

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!block.video_url) return
    const ok = await copyToClipboard(block.video_url)
    if (ok) {
      setCopied(true)
      message.success("链接已复制")
      setTimeout(() => setCopied(false), 2000)
    }
  }, [block.video_url])

  const handleDownload = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (block.video_url) downloadFile(proxyMediaUrl(block.video_url))
  }, [block.video_url])

  // ── Processing state ──
  if (block.status !== "completed" && block.status !== "failed" && !block.error) {
    return (
      <div style={{
        marginBottom: 12,
        animation: "mediaCardSlideUp 0.4s ease",
      }}>
        <div style={{
          borderRadius: "var(--radius-xl)",
          border: "1px solid var(--ice-border)",
          background: isUserMessage
            ? `${primaryColor}06`
            : "var(--ice-bg-secondary)",
          padding: "32px 24px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 16,
          position: "relative",
          overflow: "hidden",
        }}>
          {/* Animated gradient border indicator */}
          <div style={{
            position: "absolute", top: 0, left: 0, right: 0, height: 2,
            background: `linear-gradient(90deg, transparent, ${primaryColor}, ${accentColor}, transparent)`,
            animation: "processingBar 2s linear infinite",
          }} />

          {/* Spinner */}
          <div style={{
            width: 48, height: 48, borderRadius: "50%",
            border: `3px solid ${primaryColor}20`,
            borderTopColor: primaryColor,
            animation: "spin 1s linear infinite",
          }} />

          {/* Text */}
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ice-text-primary)", marginBottom: 4 }}>
              视频生成中
            </div>
            <div style={{ fontSize: 12, color: "var(--ice-text-muted)" }}>
              {block.progress && block.progress > 0
                ? `后台正在处理…（第 ${block.progress} 次状态检查）`
                : "这可能需要 1-5 分钟，请耐心等待"}
            </div>
          </div>

          {/* Progress dots */}
          <div style={{ display: "flex", gap: 6 }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{
                width: 6, height: 6, borderRadius: "50%",
                background: primaryColor,
                animation: `dotPulse 1.4s ease-in-out ${i * 0.2}s infinite`,
              }} />
            ))}
          </div>
        </div>
      </div>
    )
  }

  // ── Failed state ──
  // Coerce block.error to a string defensively: a provider may return a
  // structured error (dict), which would otherwise crash React with
  // "Objects are not valid as a React child" and blank the whole chat.
  const failedError =
    block.error == null
      ? ""
      : typeof block.error === "string"
        ? block.error
        : (() => { try { return JSON.stringify(block.error) } catch { return String(block.error) } })()
  if (block.status === "failed" || failedError) {
    return (
      <div style={{
        marginBottom: 12,
        animation: "mediaCardSlideUp 0.4s ease",
      }}>
        <div style={{
          borderRadius: "var(--radius-xl)",
          border: "1px solid rgba(239,68,68,0.25)",
          background: "rgba(239,68,68,0.04)",
          padding: "20px 24px",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}>
          <div style={{
            width: 40, height: 40, borderRadius: "50%",
            background: "rgba(239,68,68,0.1)",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <ExclamationCircleOutlined style={{ fontSize: 18, color: "#EF4444" }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: "#DC2626" }}>
              视频生成失败
            </div>
            {failedError && (
              <div style={{ fontSize: 12, color: "var(--ice-text-muted)", marginTop: 2 }}>
                {failedError}
              </div>
            )}
          </div>
          <ReloadOutlined style={{ fontSize: 18, color: "var(--ice-text-muted)", cursor: "pointer" }} />
        </div>
      </div>
    )
  }

  // ── Completed state ──
  return (
    <div style={{
      marginBottom: 12,
      animation: "mediaCardSlideUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",
    }}>
      <div style={{
        borderRadius: "var(--radius-xl)",
        overflow: "hidden",
        background: isUserMessage
          ? `${primaryColor}06`
          : "var(--ice-bg-secondary)",
        border: "1px solid var(--ice-border)",
        boxShadow: "var(--ice-shadow-sm)",
        transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
      }}
        className="media-video-card"
      >
        {/* Video player */}
        <div ref={containerRef} style={{ position: "relative", background: "#000" }}>
          {!videoSrc && (
            <div style={{
              width: "100%", height: 240,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: "#111",
              borderRadius: "var(--radius-xl) var(--radius-xl) 0 0",
              color: "var(--ice-text-muted)", fontSize: 14,
            }}>
              滚动到此处加载视频…
            </div>
          )}
          <video
            controls
            src={videoSrc || undefined}
            style={{
              width: "100%",
              maxHeight: 420,
              display: videoSrc ? "block" : "none",
              background: "#000",
              borderRadius: "var(--radius-xl) var(--radius-xl) 0 0",
            }}
            preload={videoSrc ? "metadata" : "none"}
          />
        </div>

        {/* Action bar */}
        <div style={{
          display: "flex",
          alignItems: "center",
          borderTop: "1px solid var(--ice-border)",
          background: "var(--ice-bg-card)",
        }}>
          <ActionBtn
            icon={<DownloadOutlined />}
            label="下载视频"
            primaryColor={primaryColor}
            onClick={handleDownload}
          />
          <div style={{ width: 1, alignSelf: "stretch", background: "var(--ice-border)" }} />
          <ActionBtn
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            label={copied ? "已复制" : "复制链接"}
            primaryColor={primaryColor}
            onClick={handleCopy}
          />
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MediaCard — Main Export
// ═══════════════════════════════════════════════════════════════

export default function MediaCard({
  block, primaryColor, accentColor, isUserMessage, onContentLoaded, onThumbnailClick,
}: MediaCardProps) {
  const loadedSetRef = useRef<Set<string>>(new Set())

  const handleImageLoad = useCallback((url: string) => {
    if (!loadedSetRef.current.has(url)) {
      loadedSetRef.current.add(url)
      onContentLoaded?.()
    }
  }, [onContentLoaded])

  if (block.type === "video") {
    return (
      <VideoCard
        block={block}
        primaryColor={primaryColor}
        accentColor={accentColor}
        isUserMessage={!!isUserMessage}
      />
    )
  }

  if (block.type === "image" && (block as ImageBlock).image_url) {
    const imageBlock = block as ImageBlock
    return (
      <ImageCard
        imageUrl={imageBlock.image_url}
        allImages={imageBlock.images}
        primaryColor={primaryColor}
        accentColor={accentColor}
        isUserMessage={!!isUserMessage}
        onLoad={handleImageLoad}
        onThumbnailClick={onThumbnailClick}
      />
    )
  }

  // Fallback — shouldn't happen
  return null
}

// ═══════════════════════════════════════════════════════════════
// Animations (injected once via <style>)
// ═══════════════════════════════════════════════════════════════

export function MediaCardStyles() {
  return (
    <style>{`
      @keyframes mediaCardSlideUp {
        from { opacity: 0; transform: translateY(16px) scale(0.97); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }

      @keyframes shimmer {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
      }

      @keyframes spin {
        to { transform: rotate(360deg); }
      }

      @keyframes processingBar {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
      }

      @keyframes dotPulse {
        0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
        40% { opacity: 1; transform: scale(1); }
      }

      /* Image card hover effects */
      .media-image-card:hover {
        box-shadow: var(--ice-shadow-md) !important;
        transform: translateY(-1px);
        border-color: var(--ice-border-hover) !important;
      }
      .media-image-card:hover .media-hover-overlay {
        background: rgba(0,0,0,0.2) !important;
      }
      .media-image-card:hover .media-hover-overlay > div {
        opacity: 1 !important;
        transform: translateY(0) !important;
        background: rgba(0,0,0,0.55) !important;
      }

      /* Video card hover effects */
      .media-video-card:hover {
        box-shadow: var(--ice-shadow-md) !important;
        transform: translateY(-1px);
        border-color: var(--ice-border-hover) !important;
      }

      /* Thumb hover effects */
      .media-thumb:hover {
        border-color: var(--ice-primary) !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.12);
      }
      .media-thumb:hover img {
        transform: scale(1.08) !important;
      }
      .media-thumb:hover .media-thumb-hint {
        background: rgba(0,0,0,0.35) !important;
      }
      .media-thumb:hover .media-thumb-hint > span {
        opacity: 1 !important;
        transform: scale(1) !important;
      }
    `}</style>
  )
}
