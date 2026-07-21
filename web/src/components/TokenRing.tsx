import React, { useState } from 'react';
import { Modal, Progress, Tooltip } from 'antd';

interface TokenUsage {
  system_prompt: number;
  tools: number;
  messages: number;
  mcp: number;
  skills: number;
  total: number;
  max_tokens: number;
  usage_ratio: number;
}

interface Props {
  usage: TokenUsage | null;
}

// 颜色随使用量变深
const getRingColor = (ratio: number): string => {
  if (ratio < 0.5) return '#52c41a';   // 绿
  if (ratio < 0.7) return '#faad14';   // 黄
  if (ratio < 0.9) return '#fa8c16';   // 橙
  return '#f5222d';                     // 红
};

export const TokenRing: React.FC<Props> = ({ usage }) => {
  const [showDetail, setShowDetail] = useState(false);
  
  if (!usage) {
    return (
      <div 
        className="token-ring-placeholder"
        style={{
          width: 32,
          height: 32,
          borderRadius: '50%',
          border: '2px solid #d0d0d0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 10,
          color: '#999',
        }}
      >
        --
      </div>
    );
  }
  
  const percent = (usage.usage_ratio * 100).toFixed(1);
  const color = getRingColor(usage.usage_ratio);
  const isOverLimit = usage.usage_ratio >= 0.8;
  
  return (
    <>
      <Tooltip title={`上下文用量 ${percent}%`} placement="top">
        <div 
          className="token-ring"
          onClick={() => setShowDetail(true)}
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            border: `3px solid ${color}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            background: isOverLimit ? '#fff1f0' : 'transparent',
            transition: 'all 0.3s',
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 9, color, fontWeight: 600, lineHeight: 1 }}>
            {percent}%
          </span>
        </div>
      </Tooltip>
      
      <Modal
        title="上下文用量"
        open={showDetail}
        onCancel={() => setShowDetail(false)}
        footer={null}
        width={400}
      >
        <div className="token-usage-detail">
          {/* 大数字 + 进度条 */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', marginBottom: 8 }}>
              <span style={{ fontSize: 24, fontWeight: 600, color }}>
                {percent}%
              </span>
              <span style={{ marginLeft: 8, color: '#666', fontSize: 12 }}>
                已使用 {(usage.total / 1024).toFixed(1)}K / {(usage.max_tokens / 1024).toFixed(1)}K tokens
              </span>
            </div>
            <Progress 
              percent={usage.usage_ratio * 100} 
              strokeColor={color}
              showInfo={false}
            />
          </div>
          
          {/* 分项明细 */}
          <div className="usage-items" style={{ marginTop: 16 }}>
            <UsageItem label="系统提示词" value={usage.system_prompt} color="#52c41a" />
            <UsageItem label="工具及子智能体" value={usage.tools} color="#faad14" />
            <UsageItem label="对话消息" value={usage.messages} color="#722ed1" />
            <UsageItem label="连接器及MCP" value={usage.mcp} color="#13c2c2" />
            <UsageItem label="技能" value={usage.skills} color="#eb2f96" />
          </div>
          
          {/* 超限时显示压缩提示 */}
          {isOverLimit && (
            <div style={{ marginTop: 16, padding: 12, background: '#fff1f0', borderRadius: 4 }}>
              <span style={{ color: '#f5222d', fontSize: 12 }}>
                ⚠️ 上下文使用率较高，下次对话将自动压缩历史消息
              </span>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
};

const UsageItem: React.FC<{ label: string; value: number; color: string }> = ({ label, value, color }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: 12 }}>
    <span>
      <span style={{ 
        display: 'inline-block', width: 8, height: 8, borderRadius: '50%', 
        background: color, marginRight: 8 
      }} />
      {label}
    </span>
    <span style={{ color: '#999' }}>
      ~{value >= 1024 ? `${(value/1024).toFixed(1)}k` : value}
    </span>
  </div>
);
