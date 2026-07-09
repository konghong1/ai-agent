import type { ReactNode } from 'react'

export interface PlanRowProps {
  index: number
  name: ReactNode
  fast: boolean
  count?: number | string
  ratio?: string
  resolution?: string
  onCopy?: () => void
  onDelete?: () => void
  onSettings?: () => void
}

/**
 * 出图规划列表行 —— 设计系统核心可复用组件。
 *
 * 布局（与原型 / workspace-gallery.html 一致，双行卡片）：
 *   第1行：序号 · 名称 · [极速出图/自定义] 标签
 *   第2行：数量 | 比例 | 分辨率（完整显示，永不截断）
 *   右侧：复制 / 删除 / 设置 操作（与第1行同行，固定宽度）
 *
 * 复用设计系统 .plan-row / .pr-* 样式。
 */
export function PlanRow({
  index,
  name,
  fast,
  count,
  ratio,
  resolution,
  onCopy,
  onDelete,
  onSettings,
}: PlanRowProps) {
  return (
    <div className={`plan-row ${fast ? 'fast' : 'custom'}`}>
      {/* 左侧：名称 + 参数两行 */}
      <div className="pr-body">
        {/* 第1行：序号 + 名称 + 标签（标签推到右端） */}
        <div className="pr-top">
          <span className="pr-num">{index}.</span>
          <span className="pr-name">{name}</span>
          <span className={`pr-tag ${fast ? 'fast' : 'custom'}`}>
            {fast ? '极速出图' : '自定义'}
          </span>
        </div>
        {/* 第2行：参数摘要（精致胶囊标签） */}
        <div className="pr-meta">
          <span className="pr-chip">数量 <b>{count ?? 1}</b></span>
          <span className="pr-chip">比例 <b>{ratio || (fast ? '自动' : '3:4')}</b></span>
          <span className="pr-chip">分辨率 <b>{resolution || '1K'}</b></span>
        </div>
      </div>
      {/* 右侧：操作按钮组（固定宽度，永不压缩） */}
      <div className="pr-actions">
        {onCopy && (
          <button
            className="pr-btn-icon pr-btn-copy"
            title="复制此类型"
            onClick={onCopy}
            aria-label="复制"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
          </button>
        )}
        {onDelete && (
          <button
            className="pr-btn-icon pr-btn-delete"
            title="删除此类型"
            onClick={onDelete}
            aria-label="删除"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3,6 5,6 21,6" />
              <path d="M19,6v14a2,2 0 01-2,2H7a2,2 0 01-2-2V6M8,6V4a2,2 0 012-2h4a2,2 0 012,2V6" />
            </svg>
          </button>
        )}
        {onSettings && (
          <button className="pr-set-btn" onClick={onSettings} aria-label="打开设置">
            设置
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9,18 15,12 9,6" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
