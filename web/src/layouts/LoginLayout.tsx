import React from 'react'
import { ParticleBg } from '@/components/ParticleBg'

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      height: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #0a0e17 0%, #111827 100%)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      <ParticleBg count={30} speed={0.2} opacity={0.3} />
      <div style={{ position: 'relative', zIndex: 1, width: '100%', maxWidth: 420, padding: '0 24px' }}>
        {children}
      </div>
    </div>
  )
}
