// antd v5 在 React 19 下的兼容补丁：让「静态 message/Modal」模式（如 ChatInterface）正常渲染。
// 同时 MemoryPanel 等需要命令式 toast 的页面使用 <App> + App.useApp()（antd 官方 React 19 方案），
// 二者共存：静态方法走 v5-patch 的全局 holder，App.useApp() 走 context holder。
import '@ant-design/v5-patch-for-react-19'
import { createRoot } from 'react-dom/client'
import { App as AntApp } from 'antd'
import App from './App'

// 不包 React.StrictMode：antd v5 + React 19 下，StrictMode 的 dev-only 双调用副作用会让
// 命令式 message/Modal 的 holder 被建了又拆，表现为 toast 闪现即消失或定位到屏幕外（dev 假象，生产构建无此问题）。
const root = createRoot(document.getElementById('root')!)
root.render(<AntApp><App /></AntApp>)
