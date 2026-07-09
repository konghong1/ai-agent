export interface PlannerBarProps {
  onOpen: () => void
  addLabel?: string
  addTitle?: string
}

/**
 * 策划台触发栏 —— AI 智能策划台按钮 + 添加按钮。
 * 复用设计系统 .planner-bar / .btn-planner / .btn-add-item。
 */
export function PlannerBar({
  onOpen,
  addLabel = '＋',
  addTitle = '从推荐类型中选择添加',
}: PlannerBarProps) {
  return (
    <div className="planner-bar">
      <button className="btn-planner" onClick={onOpen}>
        ✨ AI智能策划台
      </button>
      <button className="btn-add-item" title={addTitle} onClick={onOpen}>
        {addLabel}
      </button>
    </div>
  )
}
