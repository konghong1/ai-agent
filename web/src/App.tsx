import React from 'react'

export default function App() {
  return React.createElement('div', {
    style: {
      background: '#ffffff',
      color: '#000000',
      padding: '20px',
      height: '100vh'
    }
  }, 
    React.createElement('h1', null, 'HELLO WORLD - IF YOU SEE THIS, REACT WORKS'),
    React.createElement('p', null, 'CSS is disabled for testing.')
  )
}
