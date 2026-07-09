import type { ReactNode } from 'react'
import { Breadcrumb, type Crumb } from './Breadcrumb'

export interface PageHeaderProps {
  crumb?: Crumb[]
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}

/**
 * 页头 —— 面包屑 + 标题 + 副标题 + 右侧操作区。
 * 复用设计系统 .page-head / .page-title / .page-sub / .head-actions。
 */
export function PageHeader({ crumb, title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="page-head">
      <div>
        {crumb && <Breadcrumb items={crumb} />}
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-sub">{subtitle}</p>}
      </div>
      {actions && <div className="head-actions">{actions}</div>}
    </div>
  )
}
