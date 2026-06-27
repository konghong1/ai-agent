import { useRef, type CSSProperties, useState } from 'react'
import { Card, type CardProps } from 'antd'
import { motion } from 'framer-motion'

export interface IceCrystalCardProps extends CardProps {
  hoverEffect?: 'tilt' | 'glow' | 'float' | 'none'
  glassmorphism?: boolean
  animation?: 'fadeInUp' | 'fadeIn' | 'scaleIn' | 'none'
  glowColor?: string
}

const animations = {
  fadeInUp: { initial: { opacity: 0, y: 20 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.4 } },
  fadeIn: { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.3 } },
  scaleIn: { initial: { opacity: 0, scale: 0.95 }, animate: { opacity: 1, scale: 1 }, transition: { duration: 0.3 } },
  none: { initial: {}, animate: {}, transition: {} },
}

export const IceCrystalCard: React.FC<IceCrystalCardProps> = ({
  hoverEffect = 'glow',
  glassmorphism = true,
  animation = 'fadeInUp',
  glowColor,
  style,
  className,
  children,
  ...rest
}) => {
  const divRef = useRef<HTMLDivElement>(null)
  const [transform, setTransform] = useState('')

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (hoverEffect !== 'tilt' || !divRef.current) return
    const rect = divRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width - 0.5
    const y = (e.clientY - rect.top) / rect.height - 0.5
    setTransform(`perspective(800px) rotateY(${x * 8}deg) rotateX(${-y * 8}deg)`)
  }

  const handleMouseLeave = () => {
    if (hoverEffect === 'tilt') setTransform('')
  }

  const anim = animations[animation] || animations.fadeInUp
  const floatStyle: CSSProperties = hoverEffect === 'float' ? { animation: 'float 4s ease-in-out infinite' } : {}

  return (
    <motion.div
      ref={divRef}
      initial={anim.initial}
      animate={anim.animate}
      transition={anim.transition}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ transform, transition: 'transform 0.1s ease' }}
    >
      <Card
        {...rest}
        style={floatStyle}
        className={`ice-crystal-card ${glassmorphism ? 'glass' : ''} ${className || ''}`}
        data-effect={hoverEffect}
      >
        {children}
      </Card>
    </motion.div>
  )
}
