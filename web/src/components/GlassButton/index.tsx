import React from 'react'
import { Button, type ButtonProps } from 'antd'
import { LoadingOutlined } from '@ant-design/icons'

export interface GlassButtonProps extends ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  glow?: boolean
}

export const GlassButton: React.FC<GlassButtonProps> = ({
  variant = 'primary',
  glow = true,
  children,
  loading,
  className,
  ...rest
}) => {
  const baseStyles: React.CSSProperties = {
    position: 'relative',
    overflow: 'hidden',
    transition: 'all 0.2s ease',
  }

  const variantStyles: Record<string, React.CSSProperties> = {
    primary: {
      background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(0, 255, 213, 0.1))',
      color: '#e8f4f8',
      borderColor: 'rgba(0, 212, 255, 0.3)',
    },
    secondary: {
      background: 'linear-gradient(135deg, rgba(123, 104, 238, 0.2), rgba(123, 104, 238, 0.1))',
      color: '#e8f4f8',
      borderColor: 'rgba(123, 104, 238, 0.3)',
    },
    ghost: {
      background: 'rgba(255, 255, 255, 0.03)',
      color: '#8899aa',
      borderColor: 'rgba(255, 255, 255, 0.08)',
    },
    danger: {
      background: 'rgba(255, 107, 107, 0.1)',
      color: '#ff6b6b',
      borderColor: 'rgba(255, 107, 107, 0.3)',
    },
  }

  return (
    <Button
      {...rest}
      loading={loading}
      style={{ ...baseStyles, ...variantStyles[variant], ...(glow ? { boxShadow: '0 0 10px rgba(0, 212, 255, 0.1)' } : {}) }}
      className={className}
    >
      {children}
    </Button>
  )
}
