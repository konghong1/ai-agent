// antd v5 在 React 19 下的兼容补丁：修复静态 message/Modal 方法静默失效（不渲染、不报错）
import '@ant-design/v5-patch-for-react-19'
import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

const root = createRoot(document.getElementById('root')!)
root.render(React.createElement(React.StrictMode, null, React.createElement(App)))
