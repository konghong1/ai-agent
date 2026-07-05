import { useState, useEffect, useCallback, useRef } from "react"
import {
  DownloadOutlined, CloseOutlined,
  LeftOutlined, RightOutlined, CopyOutlined, CheckOutlined,
  ZoomInOutlined, ZoomOutOutlined,
} from "@ant-design/icons"
import { message } from "antd"
import { proxyMediaUrl } from "@/services/media"

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

export interface LightboxImage {
  url: string
  alt?: string
}

export interface MediaLightboxProps {
  /** All images available for navigation */
  images: LightboxImage[]
  /** Currently active image index */
  currentIndex: number
  /** Called to close the lightbox */
  onClose: () => void
  /** Called when navigating to a different image */
  onNavigate?: (index: number) => void
  /** Theme primary color */
  primaryColor: string
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
    const ta = document.createElement("textarea")
    ta.value = text
    ta.style.position = "fixed"; ta.style.opacity = "0"
    document.body.appendChild(ta)
    ta.select()
    document.execCommand("copy")
    document.body.removeChild(ta)
    return true
  }
}

// ═══════════════════════════════════════════════════════════════
// Toolbar Button
// ═══════════════════════════════════════════════════════════════

function ToolBtn({
  icon, label, onClick, active,
}: {
  icon: React.ReactNode
  label?: string
  onClick: (e: React.MouseEvent) => void
  active?: boolean
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      style={{
        background: active ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.08)",
        border: "1px solid rgba(255,255,255,0.15)",
        color: "#fff",
        borderRadius: 8,
        padding: label ? "8px 14px" : "8px",
        fontSize: 13,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        gap: label ? 6 : 0,
        backdropFilter: "blur(8px)",
        transition: "all 0.2s ease",
        lineHeight: 1,
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = "rgba(255,255,255,0.18)"
        e.currentTarget.style.borderColor = "rgba(255,255,255,0.35)"
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = active ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.08)"
        e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"
      }}
    >
      {icon}
      {label && <span>{label}</span>}
    </button>
  )
}

// ═══════════════════════════════════════════════════════════════
// MediaLightbox
// ═══════════════════════════════════════════════════════════════

export default function MediaLightbox({
  images, currentIndex, onClose, onNavigate, primaryColor,
}: MediaLightboxProps) {
  const [scale, setScale] = useState(1)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [copied, setCopied] = useState(false)
  const imageRef = useRef<HTMLImageElement>(null)

  const current = images[currentIndex]
  const hasPrev = currentIndex > 0
  const hasNext = currentIndex < images.length - 1

  // Reset zoom on image change
  useEffect(() => {
    setScale(1)
    setPosition({ x: 0, y: 0 })
  }, [currentIndex])

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      switch (e.key) {
        case "Escape":
          onClose()
          break
        case "ArrowLeft":
          if (hasPrev) onNavigate?.(currentIndex - 1)
          break
        case "ArrowRight":
          if (hasNext) onNavigate?.(currentIndex + 1)
          break
        case "+":
        case "=":
          setScale(s => Math.min(s + 0.25, 5))
          break
        case "-":
          setScale(s => Math.max(s - 0.25, 0.5))
          break
        case "0":
          setScale(1)
          setPosition({ x: 0, y: 0 })
          break
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [hasPrev, hasNext, currentIndex, onClose, onNavigate])

  // Prevent body scroll
  useEffect(() => {
    const orig = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => { document.body.style.overflow = orig }
  }, [])

  // Wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    setScale(s => Math.max(0.5, Math.min(5, s + (e.deltaY > 0 ? -0.2 : 0.2))))
  }, [])

  // Drag to pan (when zoomed)
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (scale <= 1) return
    e.preventDefault()
    setIsDragging(true)
    setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y })
  }, [scale, position])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging) return
    setPosition({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    })
  }, [isDragging, dragStart])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  // Double-click to zoom
  const handleDoubleClick = useCallback(() => {
    if (scale > 1) {
      setScale(1)
      setPosition({ x: 0, y: 0 })
    } else {
      setScale(2.5)
    }
  }, [scale])

  // Actions
  const handleDownload = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    downloadFile(proxyMediaUrl(current.url))
  }, [current.url])

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation()
    const ok = await copyToClipboard(current.url)
    if (ok) {
      setCopied(true)
      message.success("链接已复制")
      setTimeout(() => setCopied(false), 2000)
    }
  }, [current.url])

  const handleZoomIn = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setScale(s => Math.min(s + 0.5, 5))
  }, [])

  const handleZoomOut = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setScale(s => Math.max(s - 0.5, 0.5))
  }, [])

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 10000,
        background: "rgba(0,0,0,0.92)",
        backdropFilter: "blur(12px)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        animation: "lightboxIn 0.3s ease",
      }}
    >
      {/* ── Top Bar ── */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0,
        display: "flex", alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 20px",
        zIndex: 10,
        background: "linear-gradient(180deg, rgba(0,0,0,0.5) 0%, transparent 100%)",
      }}>
        {/* Left: counter + filename */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {images.length > 1 && (
            <span style={{
              color: "rgba(255,255,255,0.7)", fontSize: 13,
              fontWeight: 500,
            }}>
              {currentIndex + 1} / {images.length}
            </span>
          )}
          <span style={{
            color: "rgba(255,255,255,0.4)", fontSize: 12,
            maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {current.alt || getFilename(current.url)}
          </span>
        </div>

        {/* Right: actions */}
        <div style={{ display: "flex", gap: 6 }}>
          <ToolBtn icon={<ZoomOutOutlined />} label="" onClick={handleZoomOut} />
          <ToolBtn icon={<ZoomInOutlined />} label="" onClick={handleZoomIn} />
          <span style={{
            color: "rgba(255,255,255,0.5)", fontSize: 12,
            display: "flex", alignItems: "center", padding: "0 8px",
            fontFeatureSettings: "'tnum'",
            minWidth: 42, justifyContent: "center",
          }}>
            {Math.round(scale * 100)}%
          </span>
          <ToolBtn
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            label={copied ? "已复制" : "复制"}
            onClick={handleCopy}
          />
          <ToolBtn icon={<DownloadOutlined />} label="下载" onClick={handleDownload} />
          <ToolBtn icon={<CloseOutlined />} onClick={onClose} />
        </div>
      </div>

      {/* ── Previous Arrow ── */}
      {hasPrev && (
        <button
          onClick={e => { e.stopPropagation(); onNavigate?.(currentIndex - 1) }}
          style={{
            position: "absolute", left: 16, top: "50%", transform: "translateY(-50%)",
            zIndex: 10,
            width: 44, height: 44, borderRadius: "50%",
            background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)",
            color: "#fff", fontSize: 20, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            backdropFilter: "blur(8px)",
            transition: "all 0.2s ease",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = "rgba(255,255,255,0.18)"
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.35)"
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = "rgba(255,255,255,0.08)"
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"
          }}
        >
          <LeftOutlined />
        </button>
      )}

      {/* ── Next Arrow ── */}
      {hasNext && (
        <button
          onClick={e => { e.stopPropagation(); onNavigate?.(currentIndex + 1) }}
          style={{
            position: "absolute", right: 16, top: "50%", transform: "translateY(-50%)",
            zIndex: 10,
            width: 44, height: 44, borderRadius: "50%",
            background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)",
            color: "#fff", fontSize: 20, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            backdropFilter: "blur(8px)",
            transition: "all 0.2s ease",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = "rgba(255,255,255,0.18)"
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.35)"
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = "rgba(255,255,255,0.08)"
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"
          }}
        >
          <RightOutlined />
        </button>
      )}

      {/* ── Image Area ── */}
      <div
        onClick={e => e.stopPropagation()}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onDoubleClick={handleDoubleClick}
        style={{
          maxWidth: "90vw",
          maxHeight: "85vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default",
          transition: isDragging ? "none" : "transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
          animation: "lightboxImageIn 0.35s cubic-bezier(0.34, 1.56, 0.64, 1)",
        }}
      >
        <img
          ref={imageRef}
          src={proxyMediaUrl(current.url)}
          alt={current.alt || "Preview"}
          draggable={false}
          style={{
            maxWidth: "90vw",
            maxHeight: "85vh",
            objectFit: "contain",
            borderRadius: 6,
            transform: `scale(${scale}) translate(${position.x / scale}px, ${position.y / scale}px)`,
            transformOrigin: "center center",
            transition: isDragging ? "none" : "transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
            boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          }}
        />
      </div>

      {/* ── Bottom Thumbnail Strip (multi-image) ── */}
      {images.length > 1 && (
        <div style={{
          position: "absolute", bottom: 20, left: "50%", transform: "translateX(-50%)",
          display: "flex", gap: 4, padding: "8px 12px",
          background: "rgba(0,0,0,0.3)", backdropFilter: "blur(12px)",
          borderRadius: 12, border: "1px solid rgba(255,255,255,0.1)",
        }}>
          {images.map((img, i) => (
            <div
              key={i}
              onClick={e => { e.stopPropagation(); onNavigate?.(i) }}
              style={{
                width: 40, height: 40, borderRadius: 6,
                overflow: "hidden", cursor: "pointer",
                opacity: i === currentIndex ? 1 : 0.4,
                border: i === currentIndex
                  ? `2px solid ${primaryColor}`
                  : "2px solid transparent",
                transition: "all 0.2s ease",
              }}
              onMouseEnter={e => {
                if (i !== currentIndex) e.currentTarget.style.opacity = "0.8"
              }}
              onMouseLeave={e => {
                if (i !== currentIndex) e.currentTarget.style.opacity = "0.4"
              }}
            >
              <img
                src={proxyMediaUrl(img.url)}
                alt=""
                loading="lazy"
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            </div>
          ))}
        </div>
      )}

      {/* ── Zoom hint (bottom center) ── */}
      <div style={{
        position: "absolute", bottom: images.length > 1 ? 90 : 24,
        color: "rgba(255,255,255,0.35)", fontSize: 12,
        display: "flex", gap: 12, alignItems: "center",
      }}>
        <span>滚轮缩放</span>
        <span>·</span>
        <span>双击 {scale > 1 ? "还原" : "放大"}</span>
        <span>·</span>
        <span>ESC 关闭</span>
      </div>

      {/* Animations */}
      <style>{`
        @keyframes lightboxIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes lightboxImageIn {
          from { opacity: 0; transform: scale(0.94); }
          to { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  )
}
