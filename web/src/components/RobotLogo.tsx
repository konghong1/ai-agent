import { useState } from "react"

interface RobotLogoProps {
  collapsed: boolean
  onClick: () => void
}

/**
 * 3D 风格动画机器人 Logo
 * - 立体感：径向/线性渐变 + 高光 + 投影模拟体积与材质
 * - 交互：hover 时整体浮空、眼睛呼吸发光、右手抬起指向侧边栏方向
 * - 状态：collapsed 时右手保持抬起（提示“点我展开菜单”），展开时自然下垂
 */
export function RobotLogo({ collapsed, onClick }: RobotLogoProps) {
  const [hover, setHover] = useState(false)

  return (
    <div
      className="robot-logo"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      role="button"
      tabIndex={0}
      aria-label={collapsed ? "展开菜单" : "收起菜单"}
      title={collapsed ? "展开菜单" : "收起菜单"}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onClick()
        }
      }}
      style={{
        cursor: "pointer",
        width: 44,
        height: 44,
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 12,
        outline: "none",
        transition: "background-color 0.2s ease, transform 0.15s ease",
        userSelect: "none",
      }}
    >
      <svg
        viewBox="0 0 64 64"
        width="40"
        height="40"
        className="robot-svg"
        style={{ overflow: "visible", filter: "drop-shadow(0 3px 6px rgba(59,130,246,0.3))" }}
      >
        <defs>
          {/* 头部球体：左上高光 → 右下暗部，营造 3D 球体感 */}
          <radialGradient id="headGrad" cx="35%" cy="28%" r="80%">
            <stop offset="0%" stopColor="#bfdbfe" />
            <stop offset="45%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#1e3a8a" />
          </radialGradient>
          {/* 身体：左亮右暗的圆柱体积感 */}
          <linearGradient id="bodyGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#e0e7ff" />
            <stop offset="50%" stopColor="#818cf8" />
            <stop offset="100%" stopColor="#4338ca" />
          </linearGradient>
          {/* 眼睛发光 */}
          <radialGradient id="eyeGrad" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="45%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#0e7490" />
          </radialGradient>
          <filter id="eyeGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* 地面投影 */}
        <ellipse cx="32" cy="61" rx="13" ry="2.5" fill="rgba(30,58,138,0.18)" />

        {/* 天线 */}
        <line x1="32" y1="9" x2="32" y2="3" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />
        <circle cx="32" cy="3" r="2.6" fill="#22d3ee" filter="url(#eyeGlow)" className="robot-antenna" />

        {/* 头部（球体） */}
        <circle cx="32" cy="21" r="13" fill="url(#headGrad)" stroke="rgba(255,255,255,0.35)" strokeWidth="0.6" />
        {/* 头部高光 */}
        <ellipse cx="27" cy="16" rx="4.5" ry="3" fill="rgba(255,255,255,0.45)" />

        {/* 眼睛 */}
        <circle cx="27" cy="20" r="3.1" fill="url(#eyeGrad)" filter="url(#eyeGlow)" className="robot-eye" />
        <circle cx="37" cy="20" r="3.1" fill="url(#eyeGrad)" filter="url(#eyeGlow)" className="robot-eye" />

        {/* 嘴巴 */}
        <rect x="29" y="26.5" width="6" height="1.6" rx="0.8" fill="#1e3a8a" opacity="0.8" />

        {/* 身体 */}
        <rect x="21" y="34" width="22" height="19" rx="6" fill="url(#bodyGrad)" stroke="rgba(255,255,255,0.3)" strokeWidth="0.6" />
        {/* 身体高光 */}
        <rect x="24" y="37" width="4" height="12" rx="2" fill="rgba(255,255,255,0.25)" />

        {/* 左手（固定，自然下垂） */}
        <rect x="17" y="39" width="4" height="11" rx="2" fill="url(#bodyGrad)" />
        <circle cx="19" cy="51" r="2.6" fill="#6366f1" />

        {/* 右手（可动：collapsed 抬起指向左侧 / hover 抬起） */}
        <g
          className="robot-arm-right"
          style={{
            transform:
              collapsed || hover ? "rotate(-52deg)" : "rotate(0deg)",
            transformOrigin: "44px 39px",
            transition: "transform 0.45s cubic-bezier(0.16,1,0.3,1)",
          }}
        >
          <rect x="42" y="39" width="4" height="12" rx="2" fill="url(#bodyGrad)" />
          <circle cx="44" cy="52" r="2.6" fill="#6366f1" />
        </g>

        {/* 脚 */}
        <rect x="26" y="53" width="5" height="4" rx="2" fill="#4f46e5" />
        <rect x="33" y="53" width="5" height="4" rx="2" fill="#4f46e5" />

        {/* 指示箭头（collapsed 时显示，指向左侧侧边栏） */}
        {collapsed && (
          <g className="robot-hint" opacity={hover ? 1 : 0.55}>
            <path d="M6 32 L1 32 M6 32 L3.5 29.5 M6 32 L3.5 34.5"
              stroke="#22d3ee" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          </g>
        )}
      </svg>
    </div>
  )
}
