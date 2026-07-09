import { Fragment, type ReactNode } from 'react'

export interface Crumb {
  label: ReactNode
  onClick?: () => void
}

/**
 * 面包屑导航 —— 复用设计系统 .page-crumb 样式。
 * 最后一个 crumb 自动标记为当前页（.crumb-current，品牌色）。
 */
export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav className="page-crumb" aria-label="面包屑导航">
      {items.map((c, i) => {
        const isLast = i === items.length - 1
        const cls = isLast ? 'crumb-current' : ''
        return (
          <Fragment key={i}>
            {i > 0 && <span className="crumb-sep">/</span>}
            {c.onClick ? (
              <a
                className={cls}
                href="#"
                onClick={(e) => {
                  e.preventDefault()
                  c.onClick?.()
                }}
              >
                {c.label}
              </a>
            ) : (
              <span className={cls}>{c.label}</span>
            )}
          </Fragment>
        )
      })}
    </nav>
  )
}
