import { useEffect, useState } from 'react'
import { Drawer, Empty, message } from 'antd'
import type { GalleryType, GalleryTemplate } from '@/services/gallery'

interface Props {
  open: boolean
  onClose: () => void
  types: GalleryType[]
  templates: GalleryTemplate[]
  initialChecked: string[]
  onConfirm: (checkedIds: string[]) => void
  onApplyTemplate: (templateId: number) => void
  onDeleteTemplate: (templateId: number) => void
}

type Tab = '推荐类型' | '自定义子任务' | '已保存模板'

export default function PlannerDrawer({
  open, onClose, types, templates, initialChecked, onConfirm, onApplyTemplate, onDeleteTemplate,
}: Props) {
  const [tab, setTab] = useState<Tab>('推荐类型')
  const [checked, setChecked] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (open) {
      setChecked(new Set(initialChecked))
      setTab('推荐类型')
    }
  }, [open, initialChecked])

  const toggle = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      width={typeof window !== 'undefined' && window.innerWidth < 520 ? '100%' : 460}
      title={null}
      closable={false}
      className="g-drawer"
      styles={{ body: { padding: 0 } }}
    >
      <div className="drawer-wrap">
        <div className="drawer-head">
          <div className="drawer-tabs">
            {(['推荐类型', '自定义子任务', '已保存模板'] as Tab[]).map((t) => (
              <button
                key={t}
                className={`drawer-tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <button className="drawer-close" onClick={onClose}>✕</button>
        </div>

        <div className="drawer-body">
          {tab === '推荐类型' && (
            <div className="drawer-grid">
              {types.map((t) => (
                <div
                  key={t.id}
                  className={`dg-card ${checked.has(t.id) ? 'checked' : ''}`}
                  onClick={() => toggle(t.id)}
                >
                  <div className="dg-card-text">
                    <h4>{t.title}</h4>
                    <p>{t.desc}</p>
                  </div>
                  <div className="dg-cb">{checked.has(t.id) ? '✓' : ''}</div>
                </div>
              ))}
            </div>
          )}

          {tab === '自定义子任务' && (
            <div className="upload-note" style={{ marginTop: 8 }}>
              <span>在「推荐类型」中选择出图类型后，点击列表中每条类型的「设置 ›」即可补充自定义要求（文案、风格、数量等），无需在此单独创建子任务。</span>
            </div>
          )}

          {tab === '已保存模板' && (
            templates.length === 0 ? (
              <Empty description="暂无已保存模板" style={{ marginTop: 40 }} />
            ) : (
              <div className="drawer-grid" style={{ gridTemplateColumns: '1fr' }}>
                {templates.map((tpl) => (
                  <div key={tpl.id} className="dg-card" style={{ cursor: 'default' }}>
                    <div className="dg-card-text">
                      <h4>{tpl.name}</h4>
                      <p>{(tpl.payload?.plan_items?.length) || 0} 个策划项</p>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        className="btn-aifill"
                        onClick={() => { onApplyTemplate(tpl.id); onClose() }}
                      >应用</button>
                      <button
                        className="pr-action-icon"
                        title="删除模板"
                        onClick={() => onDeleteTemplate(tpl.id)}
                      >🗑</button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </div>

        <div className="drawer-foot">
          <span className="df-count">已勾选 <b>{checked.size}</b> 个推荐类型</span>
          <div className="df-actions">
            <button className="btn-df-cancel" onClick={onClose}>取消</button>
            <button
              className="btn-df-confirm"
              onClick={() => {
                if (checked.size === 0) {
                  message.warning('请至少选择一个策划类型')
                  return
                }
                onConfirm([...checked])
              }}
            >AI 智能策划 ({checked.size})</button>
          </div>
        </div>
      </div>
    </Drawer>
  )
}
