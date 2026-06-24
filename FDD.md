# AI Agent 管理平台 - 功能设计文档 (FDD)

| 字段 | 内容 |
|------|------|
| 产品名称 | AI Agent 管理平台 |
| 文档类型 | 功能设计 / 技术方案 |
| 版本 | v1.0 |
| 日期 | 2026-06-24 |
| 关联文档 | [PRD.md](./PRD.md) |
| 状态 | 草案 - 待评审 |

---

## 文档说明

本文档是 PRD 的技术落地版，面向开发团队。每个功能模块包含：

- **页面结构**：布局、组件树、交互流程
- **组件设计**：Props、状态、事件
- **API 对接**：请求/响应数据结构
- **后端实现**：新增/修改的代码逻辑

---

## 1. 前端架构设计

### 1.1 项目初始化

#### 安装依赖

`ash
cd web
npm install react-router-dom@^6.22 axios@^1.6 zustand@^4.5
npm install antd@^5.15 @ant-design/pro-components@^2.7
npm install framer-motion@^10.18 echarts-for-react@^3.0
npm install lucide-react@^0.370
npm install -D typescript@^5.3 @types/react @types/react-dom @types/node
`

#### vite.config.ts

`	ypescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8010', changeOrigin: true },
    },
  },
})
`

### 1.2 全局样式

#### CSS 变量 (src/styles/variables.css)

`css
:root {
  --ice-primary: #00d4ff;
  --ice-primary-10: rgba(0, 212, 255, 0.10);
  --ice-primary-30: rgba(0, 212, 255, 0.30);
  --ice-primary-dark: #0099cc;
  --ice-secondary: #7b68ee;
  --ice-accent: #00ffd5;
  --ice-bg-primary: #0a0e17;
  --ice-bg-secondary: #111827;
  --ice-bg-card: rgba(17, 24, 39, 0.85);
  --ice-bg-glass: rgba(255, 255, 255, 0.03);
  --ice-text-primary: #e8f4f8;
  --ice-text-secondary: #8899aa;
  --ice-text-muted: #556677;
  --ice-border: rgba(0, 212, 255, 0.12);
  --ice-border-hover: rgba(0, 212, 255, 0.35);
  --ice-border-active: rgba(0, 212, 255, 0.55);
  --ice-shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.3);
  --ice-shadow-md: 0 4px 24px rgba(0, 212, 255, 0.06);
  --ice-glow: 0 0 20px rgba(0, 212, 255, 0.15);
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
}
`

#### Ant Design Token 覆盖

`	ypescript
import { ConfigProvider, theme } from 'antd'

<ConfigProvider
  theme={{
    token: {
      colorPrimary: '#00d4ff',
      colorBgContainer: 'rgba(17, 24, 39, 0.92)',
      borderRadius: 12,
      fontFamily: 'Inter, system-ui, sans-serif',
    },
    algorithm: theme.darkAlgorithm,
    cssVar: true,
    hashed: false,
  }}
>
  <App />
</ConfigProvider>
`

### 1.3 全局组件

#### IceCrystalCard (冰晶卡片)

Props:
- hoverEffect: 'tilt' | 'glow' | 'float' | 'none' (默认 'glow')
- glassmorphism: boolean (默认 true)
- nimation: 'fadeInUp' | 'fadeIn' | 'scaleIn' | 'none' (默认 'fadeInUp')
- glowColor: string (默认 '#00d4ff')

效果实现:
- **glow**: hover 时边框发光 + 上浮 2px + box-shadow 冰蓝辉光
- **tilt**: framer-motion 3D perspective 跟随鼠标倾斜 (最大 8°)
- **float**: CSS @keyframes 缓慢上下浮动 (4s 周期)
- **glassmorphism**: backdrop-filter: blur(20px) + 半透明背景

#### GlassButton (玻璃按钮)

Props:
- ariant: 'primary' | 'secondary' | 'ghost' | 'danger'
- size: 'sm' | 'md' | 'lg'
- loading: boolean
- glow: boolean

效果: 渐变背景 + hover 光泽扫过动画 (::after pseudo-element)

#### ParticleBg (粒子背景)

- Canvas 绘制，40-60 个漂浮粒子
- 粒子向上缓慢飘动 + 轻微水平漂移
- 颜色: rgba(0, 212, 255, 0.1~0.4)
- 大小: 2-6px
- pointer-events: none (不阻挡交互)
- requestAnimationFrame 驱动，窗口 resize 自适应

### 1.4 状态管理 (Zustand)

#### authStore - 认证状态

`	ypescript
// src/stores/auth.ts
interface User {
  id: number
  email: string
  username: string
  role: string
}

interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: { email: string; username: string; password: string }) => Promise<void>
  logout: () => void
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('agent-token'),
  user: null,
  isAuthenticated: false,

  login: async (email, password) => {
    const res = await request.post('/auth/login', { email, password })
    localStorage.setItem('agent-token', res.data.access_token)
    set({ token: res.data.access_token, user: res.data.user, isAuthenticated: true })
  },

  register: async (data) => {
    const res = await request.post('/auth/register', data)
    localStorage.setItem('agent-token', res.data.access_token)
    set({ token: res.data.access_token, user: res.data.user, isAuthenticated: true })
  },

  logout: () => {
    localStorage.removeItem('agent-token')
    set({ token: null, user: null, isAuthenticated: false })
  },

  setUser: (user) => set({ user, isAuthenticated: !!user }),
}))
`

#### layoutStore - 布局状态

`	ypescript
// src/stores/layout.ts
interface LayoutState {
  collapsed: boolean
  sideWidth: number
  toggleCollapsed: () => void
  setSideWidth: (w: number) => void
}

export const useLayoutStore = create<LayoutState>((set) => ({
  collapsed: false,
  sideWidth: 256,
  toggleCollapsed: () => set((s) => ({ collapsed: !s.collapsed })),
  setSideWidth: (w) => set({ sideWidth: w }),
}))
`

### 1.5 API 请求封装

`	ypescript
// src/services/request.ts
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { message } from 'antd'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截: 自动附加 JWT
request.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = \Bearer \\
  }
  return config
})

// 响应拦截: 统一错误处理
request.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    if (err.response?.data?.detail) {
      message.error(err.response.data.detail)
    }
    return Promise.reject(err)
  },
)

export default request
`

### 1.6 路由配置

`	ypescript
// src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import BasicLayout from '@/layouts/BasicLayout'
import LoginLayout from '@/layouts/LoginLayout'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import AgentList from '@/pages/AgentList'
import AgentDetail from '@/pages/AgentDetail'
import KnowledgeBase from '@/pages/KnowledgeBase'
import UserManagement from '@/pages/UserManagement'
import MCPManagement from '@/pages/MCPManagement'
import SkillManagement from '@/pages/SkillManagement'
import Settings from '@/pages/Settings'

// 认证守卫
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

const menuItems = [
  { key: '/dashboard', icon: 'DashboardOutlined', label: '仪表盘' },
  { key: '/agents', icon: 'RobotOutlined', label: 'Agent 目录' },
  { key: '/knowledge-bases', icon: 'BookOutlined', label: '知识库' },
  { key: '/users', icon: 'TeamOutlined', label: '用户管理' },
  { key: '/mcp-servers', icon: 'LinkOutlined', label: 'MCP 管理' },
  { key: '/skills', icon: 'ThunderboltOutlined', label: 'Skill 管理' },
  { key: '/settings', icon: 'SettingOutlined', label: '系统设置' },
]

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginLayout><Login /></LoginLayout>} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <BasicLayout menuItems={menuItems} />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="agents" element={<AgentList />} />
          <Route path="agents/:id" element={<AgentDetail />} />
          <Route path="knowledge-bases" element={<KnowledgeBase />} />
          <Route path="users" element={<UserManagement />} />
          <Route path="mcp-servers" element={<MCPManagement />} />
          <Route path="skills" element={<SkillManagement />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
`

## 2. 页面组件详细设计

### 2.1 登录页 (src/pages/Login/index.tsx)

**组件树**:
`
Login
├── ParticleBg (背景粒子)
├── AuthCard (居中卡片)
│   ├── Logo (冰晶 Logo)
│   ├── Title ("AI Agent 管理平台")
│   ├── LoginForm / RegisterForm (切换)
│   │   ├── Input (邮箱)
│   │   ├── Input (用户名, 注册时)
│   │   ├── Input.Password (密码)
│   │   ├── GlassButton (提交)
│   └── Footer
`

**状态**:
`	ypescript
const [mode, setMode] = useState<'login' | 'register'>('login')
const [loading, setLoading] = useState(false)
const [form] = useForm()
`

**交互流程**:
1. 默认显示登录表单
2. 点击"注册" → 切换到注册表单
3. 点击提交 → setLoading(true) → 调用 API → 成功跳转 /dashboard / 失败抖动提示
4. 密码强度实时校验 (注册时)

**CSS**:
- 卡片: 200px 宽, 玻璃拟态, 居中
- 左侧: 隐藏 (移动端) / 显示 Canvas 粒子 (桌面端)
- 表单间距: 16px

---

### 2.2 仪表盘 (src/pages/Dashboard/index.tsx)

**组件树**:
`
Dashboard
├── PageHeader (欢迎语)
├── Row (4 列 StatCard)
│   ├── IceCrystalCard x4
│   │   ├── Icon
│   │   ├── Value (数字动画计数)
│   │   ├── Label
│   │   └── Trend (↑/↓ + 百分比)
├── Row (2/3 + 1/3)
│   ├── Card (趋势图)
│   │   └── ECharts (折线图)
│   └── Card (快捷操作)
│       └── GlassButton x4
└── Card (最近活动)
    └── Table (时间 | 操作 | 详情 | 操作人)
`

**数据获取**:
`	ypescript
// 并行获取所有统计数据
const [agents, kbs, users] = await Promise.all([
  request.get('/agents'),
  request.get('/knowledge-bases'),
  request.get('/users'),
])
`

**数字动画**: 使用 framer-motion 的 useSpring 实现数字从 0 到目标值的滚动效果

---

### 2.3 Agent 列表页 (src/pages/AgentList/index.tsx)

**组件树**:
`
AgentList
├── ProTable (列表)
│   ├── columns: 名称(链接) | 描述 | 模型 | 绑定KB | 状态 | 操作
│   ├── request: 调用 GET /agents
│   ├── toolBarRender: [+ 新建 Agent] 按钮
│   └── rowSelection: 批量操作
├── AgentDrawer (新建/编辑抽屉)
│   ├── Form
│   │   ├── Input (名称)
│   │   ├── TextArea (描述)
│   │   ├── TextArea (系统提示词)
│   │   ├── Select (模型)
│   │   ├── Slider (温度)
│   │   ├── Transfer (绑定知识库)
│   │   ├── Transfer (绑定 MCP)
│   │   ├── Transfer (绑定 Skill)
│   │   └── Switch (启用)
│   └── Footer: [取消] [确定]
└── ConfirmDelete (删除确认)
`

**ProTable 列定义**:
`	ypescript
const columns: ProColumns<Agent>[] = [
  { title: '名称', dataIndex: 'name', ellipsis: true, width: 160,
    render: (_, record) => <Link to={\/agents/\\}>{record.name}</Link> },
  { title: '描述', dataIndex: 'description', ellipsis: true, width: 240,
    render: (text) => text?.length > 50 ? <Tooltip title={text}>{text.slice(0, 50)}...</Tooltip> : text },
  { title: '模型', dataIndex: 'model_name', width: 120,
    render: (_, r) => <Tag color="cyan">{r.model_name}</Tag> },
  { title: '绑定知识库', dataIndex: 'knowledge_bases', width: 160,
    render: (_, r) => r.knowledge_bases?.slice(0, 2).map(kb => <Tag key={kb.id}>{kb.name}</Tag>) },
  { title: '状态', dataIndex: 'enabled', width: 80,
    render: (_, r) => <Switch checked={r.enabled} onChange={(v) => toggleEnabled(r.id, v)} /> },
  { title: '操作', width: 120, fixed: 'right',
    render: (_, r) => [
      <a key="edit" onClick={() => openDrawer(r)}>编辑</a>,
      <a key="detail" href={\/agents/\\}>详情</a>,
      <a key="delete" onClick={() => confirmDelete(r.id)} style={{color: '#ff6b6b'}}>删除</a>,
    ],
  },
]
`

---

### 2.4 Agent 详情页 (src/pages/AgentDetail/index.tsx)

**组件树**:
`
AgentDetail
├── PageHeader (← 返回 | Agent名称 | [编辑] [删除])
├── Row
│   ├── Col(6) 基本信息
│   │   ├── InfoItem (模型)
│   │   ├── InfoItem (温度)
│   │   ├── Collapsible (系统提示词)
│   │   └── Section (绑定信息)
│   │       ├── TagGroup (知识库)
│   │       ├── TagGroup (MCP)
│   │       └── TagGroup (Skill)
│   └── Col(18) 对话测试
│       ├── ThreadSelector (线程选择器)
│       ├── MessageList
│       │   ├── MessageItem (user/assistant)
│       │   │   ├── Avatar
│       │   │   ├── Content (Markdown 渲染)
│       │   │   └── SourceTags (检索来源标签)
│       └── Composer
│           ├── TextArea (输入)
│           └── SendButton
`

**对话测试实现**:
`	ypescript
function TestChat({ agentId }: { agentId: number }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(null)

  const handleSend = async () => {
    if (!input.trim() || sending) return
    setSending(true)
    const userMsg = { role: 'user', content: input, id: Date.now() }
    setMessages(prev => [...prev, userMsg])
    setInput('')

    try {
      const res = await request.post('/chat', {
        message: input,
        agent_id: agentId,
        thread_id: threadId || undefined,
      })
      const assistantMsg = {
        role: 'assistant',
        content: res.data.answer,
        id: Date.now() + 1,
        retrieval: res.data.extra?.retrieval,  // RAG 检索信息
      }
      setMessages(prev => [...prev, assistantMsg])
      setThreadId(res.data.thread_id)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="chat-container">
      <div className="message-list">
        {messages.map(msg => <MessageItem key={msg.id} {...msg} />)}
      </div>
      <div className="composer">
        <TextArea value={input} onChange={e => setInput(e.target.value)}
          onPressEnter={(e) => { if (!e.shiftKey) handleSend() }}
          autoSize={{ minRows: 1, maxRows: 4 }}
          placeholder="输入消息..."
          disabled={sending} />
        <Button type="primary" loading={sending} onClick={handleSend}>发送</Button>
      </div>
    </div>
  )
}
`

### 2.5 知识库列表页 (src/pages/KnowledgeBase/index.tsx)

**组件树**:
`
KnowledgeBaseList
├── PageHeader ("知识库管理" [+ 新建])
├── SearchBar (搜索 + 排序)
└── Grid (3列 ProCard)
    └── IceCrystalCard xN
        ├── Icon (📚)
        ├── Title (知识库名称)
        ├── Meta (文档数 | 文件夹数)
        ├── StatusTag (启用/处理中/禁用)
        └── Actions ([进入管理] [编辑] [删除])
`

**新建 KB Drawer**:
| 字段 | 类型 | 说明 |
|------|------|------|
| 名称 | Input | 1-200字符 |
| 描述 | TextArea | 最大 500 字符 |
| 嵌入模型 | Select | text-embedding-3-small / text-embedding-3-large |
| 分块大小 | NumberInput | 100-4000, 默认 500 |
| 重叠大小 | NumberInput | 0-500, 默认 50 |
| 启用 | Switch | 默认 true |

---

### 2.6 知识库详情页 (src/pages/KnowledgeBase/KBDetail.tsx) ⭐ 核心

**组件树**:
`
KBDetail
├── PageHeader ("📚 知识库名称" [编辑] [⚙ RAG 配置])
├── Row (256px + 1fr)
│   ├── Col(6) 文件夹树
│   │   └── FolderTree
│   │       ├── TreeNode (递归)
│   │       │   ├── Icon (📁/📄)
│   │       │   ├── Name
│   │       │   ├── DocCount badge
│   │       │   └── ActionIcons ([+] [编辑] [删除])
│   │       └── AddFolderButton
│   └── Col(18) 主内容区
│       └── Tabs
│           ├── Tab 1: 文档管理
│           │   ├── Toolbar ([+ 新建文件夹] [📤 上传文件])
│           │   └── ProTable (文档列表)
│           │       ├── columns: 文件名 | 大小 | 类型 | 状态 | 创建时间 | 操作
│           │       └── rowActions: 查看详情 | 删除 | 重新处理
│           ├── Tab 2: 检索测试
│           │   ├── SearchInput ([检索])
│           │   ├── ConfigRow (选择 KB, Top-K, 模式)
│           │   └── ResultList
│           │       └── SearchResultItem
│           │           ├── ScoreBadge (相关度)
│           │           ├── SourceInfo (文件名 + 路径)
│           │           ├── ContentPreview (可展开)
│           │           └── FeedbackButtons ([👍] [👎])
│           ├── Tab 3: 统计
│           │   ├── StatGrid (总文档/总分块/平均大小)
│           │   ├── StatusChart (各状态饼图)
│           │   ├── HotQueries (热门检索词)
│           │   └── AlertList (低质量文档预警)
│           └── Tab 4: RAG 配置
│               ├── Form
│               │   ├── Switch (混合检索)
│               │   ├── Switch (重排序)
│               │   ├── Select (重排序模型)
│               │   ├── Number (Top-K)
│               │   ├── Number (重排后保留)
│               │   ├── Number (最大上下文 tokens)
│               │   ├── Number (最低相关度)
│               │   └── Switch (查询改写)
│               └── SaveButton
`

**文件夹树组件实现**:
`	ypescript
function FolderTree({ kbId, parentId = null, onSelect, onAdd, onRename, onDelete }) {
  const [folders, setFolders] = useState<Folder[]>([])
  const [expandedKeys, setExpandedKeys] = useState<Set<number>>(new Set())

  useEffect(() => {
    request.get(\/knowledge-bases/\/folders/tree\).then(res => {
      setFolders(res.data)
    })
  }, [kbId])

  const buildTree = (items: Folder[]): ReactNode =>
    items.map(folder => (
      <TreeNode key={folder.id} folder={folder} depth={0}>
        {folder.children && buildTree(folder.children)}
      </TreeNode>
    ))

  return (
    <div className="folder-tree">
      {buildTree(folders)}
      <Button size="small" icon={<Plus />} onClick={() => onAdd(parentId)}>新建文件夹</Button>
    </div>
  )
}

function TreeNode({ folder, depth, children }) {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = folder.children?.length > 0

  return (
    <div style={{ paddingLeft: depth * 20 }}>
      <div className="tree-node" onClick={() => setExpanded(!expanded)}>
        <Icon name={hasChildren ? (expanded ? 'ChevronDown' : 'ChevronRight') : 'File'} />
        <span>{folder.name}</span>
        <Badge count={folder.document_count} />
        <ActionMenu>
          <Edit onClick={() => onRename(folder.id)} />
          <Delete onClick={() => onDelete(folder.id)} />
          <Plus onClick={() => onAdd(folder.id)} />
        </ActionMenu>
      </div>
      {expanded && children}
    </div>
  )
}
`

**文件上传组件**:
`	ypescript
function FileUpload({ kbId, folderId, onComplete }) {
  const [dragOver, setDragOver] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState<Record<number, number>>({})

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const newFiles = Array.from(e.dataTransfer.files).slice(0, 10)
    setFiles(prev => [...prev, ...newFiles])
  }

  const handleUpload = async () => {
    setUploading(true)
    for (const file of files) {
      const formData = new FormData()
      formData.append('file', file)
      if (folderId) formData.append('folder_id', String(folderId))

      try {
        const res = await request.post(\/knowledge-bases/\/upload\, formData, {
          onUploadProgress: (e) => {
            setProgress(prev => ({ ...prev, [file.name]: Math.round(e.progress * 100) }))
          },
        })
        // 上传成功，开始轮询处理状态
        pollDocumentStatus(kbId, res.data.document_id)
      } finally {
        setUploading(false)
      }
    }
  }

  const pollDocumentStatus = async (kbId, docId) => {
    const interval = setInterval(async () => {
      const res = await request.get(\/knowledge-bases/\/documents\)
      const doc = res.data.find(d => d.id === docId)
      if (doc && ['ready', 'failed'].includes(doc.status)) {
        clearInterval(interval)
        onComplete(doc.status)
      }
    }, 2000)
  }

  return (
    <div
      className={upload-zone \}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <UploadIcon />
      <p>拖拽文件到此处 或 点击选择</p>
      <p className="hint">支持 PDF, DOCX, TXT, MD, Code · 最大 50MB</p>
      <input type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.json,.py,.js,.ts"
        style={{ display: 'none' }} onChange={(e) => setFiles(Array.from(e.target.files || []))} />
    </div>
  )
}
`

### 2.7 用户管理页 (src/pages/UserManagement/index.tsx)

**组件树**:
`
UserManagement
├── PageHeader ("用户管理" [+ 新建用户])
├── Filters (搜索 | 角色筛选 | 状态筛选)
└── ProTable
    ├── columns: 用户名 | 邮箱 | 角色(Tag) | 状态(Switch) | 操作
    ├── request: GET /users
    ├── rowSelection: 批量禁用/启用
    └── drawer: UserDrawer
        ├── Form
        │   ├── Input (用户名)
        │   ├── Input.Email (邮箱)
        │   ├── Input.Password (密码, 编辑时可选)
        │   ├── Select (角色: admin/editor/user)
        │   └── Switch (启用)
        └── Footer: [取消] [确定]
`

**角色权限矩阵**:

| 页面 | admin | editor | user |
|------|-------|--------|------|
| 仪表盘 | ✅ | ✅ | ✅ |
| Agent 目录 | ✅ 管理 | ✅ 管理 | ✅ 查看+对话 |
| 知识库 | ✅ 管理 | ✅ 管理 | ✅ 查看 |
| 用户管理 | ✅ 全部 | ❌ | ❌ |
| MCP 管理 | ✅ | ✅ | ❌ |
| Skill 管理 | ✅ | ✅ | ❌ |
| 系统设置 | ✅ | ❌ | ❌ |

---

### 2.8 MCP 管理页 (src/pages/MCPManagement/index.tsx)

**组件树**:
`
MCPManagement
├── PageHeader ("MCP Server" [+ 添加])
└── ProList
    └── MCPListItem xN
        ├── Title (名称)
        ├── Meta (传输方式 | 命令/URL)
        ├── StatusTag (启用/禁用)
        └── Actions ([编辑] [测试连接] [删除])
`

**新建 Drawer**:
| 字段 | 类型 | 必填 | 条件 |
|------|------|------|------|
| 名称 | Input | 是 | - |
| 传输方式 | Select(stdio/http) | 是 | - |
| 命令 | Input | 条件 | stdio 时必填 |
| 参数 | TagInput | 否 | stdio 时可选 |
| 环境变量 | KeyValueEditor | 否 | - |
| URL | Input.URL | 条件 | http 时必填 |
| 启用 | Switch | 是 | 默认 true |

---

### 2.9 Skill 管理页 (src/pages/SkillManagement/index.tsx)

结构与 MCP 管理类似，字段不同:

| 字段 | 说明 |
|------|------|
| 名称 | 技能唯一标识 |
| 标题 | 显示名称 |
| 描述 | 用途说明 |
| 源类型 | Select(local/remote) |
| 路径 | 本地路径或远程 URL |
| 启用 | Switch |

---

### 2.10 系统设置页 (src/pages/Settings/index.tsx)

**Tab 结构**:

**Tab 1: 全局配置**
`
┌──────────────────────────────────────────┐
│ 键          │ 值           │ 操作       │
├─────────────┼──────────────┼────────────┤
│ default_model │ gpt-4o-mini │ [编辑][删除]│
│ max_upload  │ 52428800     │ [编辑][删除]│
│ rag_top_k   │ 5            │ [编辑][删除]│
└──────────────────────────────────────────┘
[+ 添加设置]
`

**Tab 2: API 配置**
`
OpenAI API Key: [________________________] [保存]
OpenAI Base URL: [______________________] [保存]
OpenAI Model:   [gpt-4o-mini___________] [保存]
`

**Tab 3: 主题**
`
选择主题:
○ 冰晶默认 (当前)
○ 深邃星空
○ 极简白
`

## 3. 后端 RAG 核心实现

### 3.1 新增数据模型 (app/models.py)

`python
# 新增: RAG 反馈表
class KBFeedback(Base):
    __tablename__ = "kb_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    thread_id: Mapped[str] = mapped_column(String(80))
    chunk_id: Mapped[int] = mapped_column(ForeignKey("kb_chunks.id", ondelete="CASCADE"))
    is_helpful: Mapped[bool]  # True=有用 False=无用
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

# 新增: 检索日志表
class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(80))
    query: Mapped[str] = mapped_column(Text)
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    top_k: Mapped[int]
    hit_count: Mapped[int]
    avg_score: Mapped[float]
    took_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
`

### 3.2 KnowledgeBase 模型扩展

在 KnowledgeBase 类中添加 rag_config 字段:

`python
class KnowledgeBase(TimestampMixin, Base):
    # ... 现有字段 ...
    rag_config: Mapped[dict] = mapped_column(SA_JSON, default={
        "hybrid_search": True,
        "rerank_enabled": True,
        "rerank_model": "bge-reranker-base",
        "top_k": 20,
        "rerank_top_k": 10,
        "mmr_enabled": True,
        "mmr_threshold": 0.5,
        "max_context_tokens": 4000,
        "min_relevance_score": 0.3,
        "query_rewrite": True,
        "include_sources": True,
    })
`

### 3.3 新增 RAG 服务类 (app/services.py)

`python
# ============================================================
# RAG Core Services (新增)
# ============================================================

class QueryRewriter:
    """查询改写: 将用户自然语言查询转换为更适合检索的形式"""

    @staticmethod
    def rewrite(query: str, kb_name: str = "", llm_client = None) -> str:
        """
        改写策略:
        1. 提取关键词
        2. 扩展同义词
        3. 补全省略成分

        示例:
        输入: "怎么部署这个系统?"
        输出: "系统部署 安装配置 步骤 教程 环境搭建"
        """
        if llm_client:
            # 使用 LLM 进行智能改写
            prompt = f"""改写以下查询为更适合知识库检索的形式。
知识库名称: {kb_name}
原始查询: {query}
只输出改写后的关键词，用空格分隔，不要解释。"""
            response = llm_client.generate(prompt)
            return response.strip()
        else:
            # 简单规则改写: 去除停用词, 保留实词
            return QueryRewriter._rule_based_rewrite(query)

    @staticmethod
    def _rule_based_rewrite(query: str) -> str:
        """基于规则的简单改写"""
        stop_words = {'怎么', '如何', '什么', '为什么', '呢', '吗', '的', '了', '是'}
        words = [w for w in query.split() if w not in stop_words]
        return ' '.join(words) or query


class HybridRetriever:
    """混合检索: 向量检索 + 关键词检索 + RRF 融合"""

    def __init__(self, kb: KnowledgeBase, db: Session):
        self.kb = kb
        self.db = db
        self.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    def retrieve(
        self,
        query: str,
        top_k: int = 20,
        rerank_top_k: int = 10,
        folder_id: int | None = None,
    ) -> list[dict]:
        """
        执行混合检索, 返回排序后的结果
        """
        # 第1路: 向量检索
        vector_hits = self._vector_search(query, top_k=top_k, folder_id=folder_id)

        # 第2路: 关键词检索 (BM25-like)
        keyword_hits = self._keyword_search(query, top_k=top_k, folder_id=folder_id)

        # RRF 融合
        fused = self._rrf_fusion(vector_hits, keyword_hits, k=60)

        # MMR 去重
        if fused and self.kb.rag_config.get('mmr_enabled', True):
            fused = self._mmr_deduplicate(fused, threshold=self.kb.rag_config.get('mmr_threshold', 0.5))

        # 重排序
        if fused and self.kb.rag_config.get('rerank_enabled', True):
            fused = self._rerank(query, fused[:rerank_top_k])

        # 过滤低分结果
        min_score = self.kb.rag_config.get('min_relevance_score', 0.3)
        fused = [h for h in fused if h['score'] >= min_score]

        return fused[:top_k]

    def _vector_search(self, query: str, top_k: int, folder_id: int | None) -> list[dict]:
        """向量检索 (语义相似度)"""
        embeddings = get_embeddings(self.kb.embedding_model)
        query_vec = embeddings.embed_query(query)

        coll = self.chroma_client.get_collection(f"kb_{self.kb.id}")
        where = {"kb_id": str(self.kb.id)}
        if folder_id:
            where["folder_id"] = str(folder_id)

        results = coll.query(
            query_embeddings=[query_vec],
            n_results=top_k * 2,  # 多取一些用于后续过滤
            where=where,
        )

        hits = []
        for i, (dist, doc) in enumerate(zip(results['distances'][0], results['documents'][0])):
            hits.append({
                'type': 'vector',
                'score': 1 - dist,  # 转换为相似度
                'content': doc,
                'metadata': results['metadatas'][0][i],
                'vector_id': results['ids'][0][i],
            })
        return hits

    def _keyword_search(self, query: str, top_k: int, folder_id: int | None) -> list[dict]:
        """关键词检索 (基于 SQLite 全文匹配)"""
        keywords = query.split()
        if not keywords:
            return []

        # 在 KBChunk.content 中做 LIKE 匹配
        chunks = self.db.scalars(
            select(KBChunk).where(
                KBChunk.kb_id == self.kb.id,
                or_(*[KBChunk.content.like(f'%{kw}%') for kw in keywords]),
            )
        ).all()

        hits = []
        for chunk in chunks[:top_k]:
            doc = chunk.document
            hits.append({
                'type': 'keyword',
                'score': self._calc_keyword_score(chunk.content, keywords),
                'content': chunk.content,
                'metadata': {
                    'document_id': doc.id,
                    'document_name': doc.original_filename,
                    'folder_path': '',
                    'kb_id': self.kb.id,
                    'folder_id': chunk.folder_id,
                },
                'vector_id': chunk.vector_id,
            })
        return hits

    def _calc_keyword_score(self, content: str, keywords: list[str]) -> float:
        """计算关键词匹配分数"""
        content_lower = content.lower()
        score = sum(1 for kw in keywords if kw.lower() in content_lower)
        return score / len(keywords) if keywords else 0

    def _rrf_fusion(self, vector_hits: list, keyword_hits: list, k: int = 60) -> list[dict]:
        """Reciprocal Rank Fusion 融合排序"""
        rank_map: dict[str, float] = {}

        for i, hit in enumerate(vector_hits):
            vid = hit['vector_id']
            rank_map[vid] = rank_map.get(vid, 0) + k / (k + i + 1)

        for i, hit in enumerate(keyword_hits):
            vid = hit['vector_id']
            rank_map[vid] = rank_map.get(vid, 0) + k / (k + i + 1)

        # 合并结果
        merged = {}
        for hit in vector_hits + keyword_hits:
            vid = hit['vector_id']
            if vid not in merged:
                merged[vid] = {**hit, 'rrf_score': 0}
            merged[vid]['rrf_score'] = rank_map.get(vid, 0)
            # 标记来源
            if hit['type'] == 'vector' and hit['type'] == 'keyword':
                merged[vid]['hit_source'] = 'both'
            else:
                merged[vid]['hit_source'] = hit['type']

        # 按 RRF 分数排序
        return sorted(merged.values(), key=lambda x: x['rrf_score'], reverse=True)

    def _mmr_deduplicate(self, hits: list[dict], threshold: float = 0.5) -> list[dict]:
        """Maximal Marginal Relevance 去重"""
        if not hits:
            return []

        import numpy as np
        embeddings = get_embeddings(self.kb.embedding_model)
        selected = [hits[0]]
        remaining = hits[1:]

        while remaining:
            best_idx = 0
            best_score = -1

            for i, candidate in enumerate(remaining):
                cand_emb = np.array(embeddings.embed_query(candidate['content']))
                relevance = np.dot(cand_emb, cand_emb)  # 简化: 自身相似度

                max_similarity = 0
                for sel in selected:
                    sel_emb = np.array(embeddings.embed_query(sel['content']))
                    sim = float(np.dot(cand_emb, sel_emb) / (np.linalg.norm(cand_emb) * np.linalg.norm(sel_emb) + 1e-8))
                    max_similarity = max(max_similarity, sim)

                mmr_score = relevance - threshold * max_similarity
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected[:10]  # 保留前10个

    def _rerank(self, query: str, hits: list[dict]) -> list[dict]:
        """Cross-Encoder 重排序"""
        if not hits:
            return []

        reranker_model = self.kb.rag_config.get('rerank_model', 'bge-reranker-base')

        if reranker_model == 'bge-reranker-base':
            # 使用本地模型
            return self._local_rerank(query, hits)
        elif reranker_model.startswith('cohere'):
            # 调用 Cohere API
            return self._cohere_rerank(query, hits)
        else:
            # 降级: 直接按 RRF 分数排序
            return sorted(hits, key=lambda x: x.get('rrf_score', 0), reverse=True)

    def _local_rerank(self, query: str, hits: list[dict]) -> list[dict]:
        """本地 Cross-Encoder 重排"""
        try:
            from sentence_transformers import CrossEncoder
            model = CrossEncoder('BAAI/bge-reranker-base')

            pairs = [[query, h['content']] for h in hits]
            scores = model.predict(pairs)

            for hit, score in zip(hits, scores):
                hit['rerank_score'] = float(score)
                hit['score'] = score  # 覆盖原分数

            return sorted(hits, key=lambda x: x['rerank_score'], reverse=True)
        except ImportError:
            # 模型未安装, 降级
            return sorted(hits, key=lambda x: x.get('rrf_score', 0), reverse=True)
`

### 3.4 上下文构建器 (app/services.py)

`python
class ContextBuilder:
    """将检索结果组装为 LLM 可用的上下文"""

    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens

    def build(
        self,
        query: str,
        hits: list[dict],
        include_sources: bool = True,
    ) -> tuple[str, list[dict]]:
        """
        返回: (上下文文本, 来源信息列表)
        """
        if not hits:
            return "", []

        context_parts = []
        sources = []

        for i, hit in enumerate(hits, 1):
            content = hit['content']
            meta = hit.get('metadata', {})

            # 截断过长的内容
            content = self._truncate_to_tokens(content, self.max_tokens // len(hits))

            # 构建来源标注
            source_tag = ""
            if include_sources:
                doc_name = meta.get('document_name', 'Unknown')
                score = hit.get('score', 0)
                folder_path = meta.get('folder_path', '')
                source_tag = f"[来源: {doc_name}, 相关度: {score:.0%}]"
                if folder_path:
                    source_tag += f" ({folder_path})"

            context_parts.append(f"{source_tag}\\n{content}\\n")

            sources.append({
                'document_name': meta.get('document_name', ''),
                'folder_path': meta.get('folder_path', ''),
                'score': hit.get('score', 0),
                'rerank_score': hit.get('rerank_score'),
                'hit_source': hit.get('hit_source', 'vector'),
            })

        context = "\\n=== 检索到的相关知识 ===\\n\\n" + "".join(context_parts)
        return context, sources

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """简单按字符截断 (近似 token 数)"""
        chars_per_token = 3.5  # 英文约 3.5 chars/token, 中文约 1 char/token
        max_chars = int(max_tokens * chars_per_token)
        if len(text) > max_chars:
            return text[:max_chars] + "... [内容过长, 已截断]"
        return text
`

### 3.5 RAG 系统提示词 (app/services.py)

`python
RAG_SYSTEM_PROMPT = """你是一个基于知识库的智能问答助手。

## 回答规则

1. **优先使用检索到的知识**: 当提供了检索结果时, 必须基于这些内容回答问题
2. **必须引用来源**: 每个关键信息后面标注 [来源: 文件名]
3. **不知道就说不知道**: 如果检索结果中没有相关信息, 明确告知用户
4. **不要编造答案**: 即使你觉得知道答案, 也要以检索结果为准
5. **综合多来源**: 多个文档有相关信息时, 综合后给出完整回答
6. **指出矛盾**: 不同文档有冲突信息时, 告知用户并列出各方说法

## 回答风格

- 结构化, 条理清晰
- 适当使用 Markdown 格式
- 引用具体数据和事实
- 如果问题超出知识库范围, 告知用户并尝试用通用知识回答
"""
`

### 3.6 修改 Agent 编排层 (app/agent.py)

`python
def ask_agent(db: Session, user_id: int, agent_id: int, message: str, thread_id: str | None = None) -> tuple[str, str, dict]:
    """RAG 增强的 Agent 对话"""
    settings = get_settings()
    agent_config = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == user_id))
    if not agent_config:
        raise HTTPException(status_code=404, detail="Agent not found.")

    thread = _get_or_create_thread(db, user_id, agent_id, message, thread_id)
    db.add(Message(thread_id=thread.id, role="user", content=message))
    db.flush()

    # === RAG 检索 ===
    rag_context = None
    retrieval_info = []
    kb_service = KnowledgeBaseService

    # 获取 Agent 绑定的知识库
    bound_kbs = db.scalars(
        select(KnowledgeBase).where(KnowledgeBase.id.in_([kb.id for kb in agent_config.knowledge_bases]))
    ).all()

    if bound_kbs:
        # 对每个绑定的 KB 执行检索
        all_hits = []
        for kb in bound_kbs:
            retriever = HybridRetriever(kb, db)
            hits = retriever.retrieve(query=message, top_k=kb.rag_config.get('top_k', 20))
            for h in hits:
                h['metadata']['kb_name'] = kb.name
            all_hits.extend(hits)

        # 按分数排序取 Top-K
        all_hits.sort(key=lambda x: x.get('score', 0), reverse=True)
        all_hits = all_hits[:kb.rag_config.get('top_k', 5)]

        if all_hits:
            # 组装上下文
            max_tokens = kb.rag_config.get('max_context_tokens', 4000)
            builder = ContextBuilder(max_tokens=max_tokens)
            rag_context, retrieval_info = builder.build(
                query=message,
                hits=all_hits,
                include_sources=kb.rag_config.get('include_sources', True),
            )

    # 构建消息
    stored_messages = list(db.scalars(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
    ))
    langchain_messages = [
        {"role": "system", "content": agent_config.system_prompt or RAG_SYSTEM_PROMPT},
        *([{"role": "user", "content": msg.content} for msg in stored_messages if msg.role == "user"],
          {"role": "assistant", "content": msg.content} for msg in stored_messages if msg.role == "assistant"),
    ]

    # 注入 RAG 上下文
    if rag_context:
        langchain_messages.append({
            "role": "user",
            "content": f"\\n\\n<knowledge_context>\\n{rag_context}\\n</knowledge_context>\\n\\n请基于以上知识回答用户的问题。",
        })

    # 记录检索日志
    if retrieval_info:
        log_entry = RetrievalLog(
            thread_id=thread.id,
            query=message,
            kb_id=bound_kbs[0].id if bound_kbs else None,
            top_k=len(all_hits),
            hit_count=len(retrieval_info),
            avg_score=sum(h.get('score', 0) for h in retrieval_info) / len(retrieval_info),
            took_ms=0,  # 实际计时在调用处
        )
        db.add(log_entry)

    # 调用 Agent
    llm = ChatOpenAI(
        model=agent_config.model_name or settings.openai_model,
        temperature=agent_config.temperature,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    agent = create_agent(model=llm, tools=get_tools(), system_prompt="", name=f"agent-{agent_config.id}")

    result = agent.invoke({"messages": langchain_messages})
    answer_raw = result["messages"][-1].content
    answer_text, blocks = _extract_blocks(answer_raw)

    msg = Message(
        thread_id=thread.id, role="assistant", content=answer_text,
        extra={"blocks": blocks, "retrieval": retrieval_info, "has_kb_context": rag_context is not None},
    )
    db.add(msg)
    db.commit()
    return answer_text, thread.id, blocks
`

### 3.7 新增 API 端点 (app/api.py)

`python
# ---- RAG 检索 API ----

@router.post("/knowledge-bases/search", response_model=list[KBSearchResult])
def search_knowledge_base_rag(
    payload: KBSearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """RAG 增强的知识库检索, 返回带分数的详细结果"""
    kb = KnowledgeBaseService.get_kb(db, payload.kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    start_time = time.time()

    # 混合检索
    retriever = HybridRetriever(kb, db)
    hits = retriever.retrieve(
        query=payload.query,
        top_k=kb.rag_config.get('top_k', 20),
        rerank_top_k=kb.rag_config.get('rerank_top_k', 10),
        folder_id=payload.folder_id,
    )

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 记录检索日志
    log = RetrievalLog(
        thread_id="",  # 检索测试页没有 thread_id
        query=payload.query,
        kb_id=kb.id,
        top_k=len(hits),
        hit_count=len(hits),
        avg_score=sum(h.get('score', 0) for h in hits) / max(len(hits), 1),
        took_ms=elapsed_ms,
    )
    db.add(log)
    db.commit()

    return [
        {
            'chunk_id': None,
            'vector_id': h['vector_id'],
            'document_id': h['metadata'].get('document_id'),
            'document_name': h['metadata'].get('document_name', ''),
            'folder_path': h['metadata'].get('folder_path', ''),
            'page_number': None,
            'chunk_index': 0,
            'content': h['content'],
            'score': h['score'],
            '_elapsed_ms': elapsed_ms,
        }
        for h in hits
    ]


# ---- 检索反馈 API ----

@router.post("/retrieval-feedback")
def submit_feedback(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交检索结果反馈"""
    feedback = KBFeedback(
        user_id=current_user.id,
        thread_id=payload['thread_id'],
        chunk_id=payload['chunk_id'],
        is_helpful=payload['is_helpful'],
        comment=payload.get('comment'),
    )
    db.add(feedback)
    db.commit()
    return {"status": "ok"}


# ---- KB 统计 API ----

@router.get("/knowledge-bases/{kb_id}/stats")
def get_kb_stats(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取知识库统计信息"""
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    total_docs = db.scalar(select(func.count(KBDocument.id)).where(KBDocument.kb_id == kb_id))
    total_chunks = db.scalar(select(func.count(KBChunk.id)).where(KBChunk.kb_id == kb_id))
    status_counts = db.execute(
        select(KBDocument.status, func.count(KBDocument.id))
        .where(KBDocument.kb_id == kb_id)
        .group_by(KBDocument.status)
    ).all()

    # 热门检索词 (从 RetrievalLog 聚合)
    hot_queries = db.execute(
        select(RetrievalLog.query, func.count(RetrievalLog.id).label('cnt'))
        .where(RetrievalLog.kb_id == kb_id)
        .group_by(RetrievalLog.query)
        .order_by(desc('cnt'))
        .limit(10)
    ).all()

    return {
        "total_documents": total_docs or 0,
        "total_chunks": total_chunks or 0,
        "avg_chunks_per_doc": round(total_chunks / max(total_docs, 1), 1),
        "status_breakdown": dict(status_counts),
        "hot_queries": [str(q.query) for q in hot_queries],
    }
`

### 3.8 新增 Pydantic Schema (app/schemas.py)

`python
class RAGConfigUpdate(BaseModel):
    hybrid_search: bool | None = None
    rerank_enabled: bool | None = None
    rerank_model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank_top_k: int | None = Field(default=None, ge=1, le=30)
    mmr_enabled: bool | None = None
    mmr_threshold: float | None = Field(default=None, ge=0, le=1)
    max_context_tokens: int | None = Field(default=None, ge=500, le=16000)
    min_relevance_score: float | None = Field(default=None, ge=0, le=1)
    query_rewrite: bool | None = None
    include_sources: bool | None = None


class RetrievalFeedbackRequest(BaseModel):
    thread_id: str
    chunk_id: int
    is_helpful: bool
    comment: str | None = ""


class RetrievalLogRead(BaseModel):
    id: int
    thread_id: str
    query: str
    rewritten_query: str | None
    kb_id: int
    top_k: int
    hit_count: int
    avg_score: float
    took_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
`

### 3.9 新增 requirements 依赖

`
# RAG 增强依赖
sentence-transformers>=2.2.0    # Cross-Encoder reranker
numpy>=1.24.0                   # MMR 计算
`

## 4. 前端服务层设计

### 4.1 API 服务模块

`	ypescript
// src/services/agent.ts
import request from './request'

export interface Agent {
  id: number
  name: string
  description: string
  system_prompt: string
  model_provider: string
  model_name: string
  temperature: number
  enabled: boolean
  created_at: string
  updated_at: string
  knowledge_bases?: KBBrief[]
}

export interface AgentCreate {
  name: string
  description?: string
  system_prompt?: string
  model_name?: string
  temperature?: number
  enabled?: boolean
  knowledge_base_ids?: number[]
}

export const agentService = {
  list: () => request.get<Agent[]>('/agents'),
  create: (data: AgentCreate) => request.post<Agent>('/agents', data),
  update: (id: number, data: Partial<AgentCreate>) => request.patch<Agent>(\/agents/\\, data),
  remove: (id: number) => request.delete(\/agents/\\),
  chat: (agentId: number, message: string, threadId?: string) =>
    request.post('/chat', { agent_id: agentId, message, thread_id: threadId }),
  getThreads: (agentId: number) => request.get(\/agents/\/threads\),
  createThread: (agentId: number, title?: string) =>
    request.post(\/agents/\/threads\, { title: title || 'New chat' }),
}

// src/services/knowledgeBase.ts
export interface KnowledgeBase {
  id: number
  name: string
  description: string
  embedding_model: string
  chunk_size: number
  chunk_overlap: number
  enabled: boolean
  rag_config?: Record<string, any>
  created_at: string
}

export interface KBFolder {
  id: number
  name: string
  description: string
  parent_id: number | null
  children: KBFolder[]
  document_count: number
}

export interface KBDocument {
  id: number
  kb_id: number
  folder_id: number | null
  original_filename: string
  file_type: string
  file_size: number
  status: 'pending' | 'processing' | 'ready' | 'failed'
  error_message: string | null
  created_at: string
}

export const knowledgeBaseService = {
  list: () => request.get<KnowledgeBase[]>('/knowledge-bases'),
  create: (data: Partial<KnowledgeBase>) => request.post<KnowledgeBase>('/knowledge-bases', data),
  update: (id: number, data: Partial<KnowledgeBase>) => request.patch<KnowledgeBase>(\/knowledge-bases/\\, data),
  remove: (id: number) => request.delete(\/knowledge-bases/\\),
  getFolders: (kbId: number) => request.get<KBFolder[]>(\/knowledge-bases/\/folders/tree\),
  createFolder: (kbId: number, data: { name: string; parent_id?: number }) =>
    request.post(\/knowledge-bases/\/folders\, data),
  listDocuments: (kbId: number, folderId?: number) =>
    request.get<KBDocument[]>(\/knowledge-bases/\/documents\, { params: { folder_id: folderId } }),
  uploadFile: (kbId: number, file: File, folderId?: number) => {
    const formData = new FormData()
    formData.append('file', file)
    if (folderId) formData.append('folder_id', String(folderId))
    return request.post(\/knowledge-bases/\/upload\, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  deleteDocument: (kbId: number, docId: number) =>
    request.delete(\/knowledge-bases/\/documents/\\),
  search: (kbId: number, query: string, topK: number = 5) =>
    request.post('/knowledge-bases/search', { kb_id: kbId, query, top_k: topK }),
  getStats: (kbId: number) => request.get(\/knowledge-bases/\/stats\),
}

// src/services/user.ts
export const userService = {
  list: () => request.get('/users'),
  update: (id: number, data: { role?: string; enabled?: boolean }) =>
    request.patch(\/users/\\, data),
  remove: (id: number) => request.delete(\/users/\\),
}

// src/services/settings.ts
export const settingsService = {
  list: () => request.get('/settings'),
  create: (data: { key: string; value: string; description?: string }) =>
    request.post('/settings', data),
  update: (key: string, data: { value: string }) =>
    request.patch(\/settings/\\, data),
  remove: (key: string) => request.delete(\/settings/\\),
}

// src/services/mcp.ts
export const mcpService = {
  list: () => request.get('/mcp-servers'),
  create: (data: any) => request.post('/mcp-servers', data),
  update: (id: number, data: any) => request.patch(\/mcp-servers/\\, data),
  remove: (id: number) => request.delete(\/mcp-servers/\\),
}

// src/services/skill.ts
export const skillService = {
  list: () => request.get('/skills'),
  create: (data: any) => request.post('/skills', data),
  update: (id: number, data: any) => request.patch(\/skills/\\, data),
  remove: (id: number) => request.delete(\/skills/\\),
}
`

## 5. 布局组件详细设计

### 5.1 BasicLayout (主布局)

`	ypescript
// src/layouts/BasicLayout.tsx
import { Layout, Menu, Avatar, Dropdown, Space } from 'antd'
import {
  DashboardOutlined, RobotOutlined, BookOutlined, TeamOutlined,
  LinkOutlined, ThunderboltOutlined, SettingOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined, LogoutOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { useLayoutStore } from '@/stores/layout'
import ParticleBg from '@/components/ParticleBg'

const { Sider, Header, Content } = Layout

const menuMap: Record<string, { icon: React.ReactNode; label: string }> = {
  '/dashboard': { icon: <DashboardOutlined />, label: '仪表盘' },
  '/agents': { icon: <RobotOutlined />, label: 'Agent 目录' },
  '/knowledge-bases': { icon: <BookOutlined />, label: '知识库' },
  '/users': { icon: <TeamOutlined />, label: '用户管理' },
  '/mcp-servers': { icon: <LinkOutlined />, label: 'MCP 管理' },
  '/skills': { icon: <ThunderboltOutlined />, label: 'Skill 管理' },
  '/settings': { icon: <SettingOutlined />, label: '系统设置' },
}

export default function BasicLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { collapsed, toggleCollapsed } = useLayoutStore()
  const { user, logout } = useAuthStore()

  const menuItems = Object.entries(menuMap).map(([path, { icon, label }]) => ({
    key: path,
    icon,
    label,
  }))

  const userMenu = {
    items: [
      { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
      { type: 'divider' as const },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录',
        onClick: () => { logout(); navigate('/login') } },
    ],
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <ParticleBg />
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={toggleCollapsed}
        width={256}
        theme="dark"
        style={{
          background: 'rgba(10, 14, 23, 0.95)',
          borderRight: '1px solid var(--ice-border)',
        }}
      >
        <div className="logo" style={{ padding: '20px', textAlign: 'center' }}>
          <h2 style={{ color: '#00d4ff', margin: 0 }}>AI Agent</h2>
          <small style={{ color: '#8899aa' }}>管理平台</small>
        </div>
        <Menu
          mode="inline"
          items={menuItems}
          selectedKeys={[location.pathname]}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 'none' }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: 'rgba(10, 14, 23, 0.85)',
            backdropFilter: 'blur(20px)',
            borderBottom: '1px solid var(--ice-border)',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggleCollapsed}
            style={{ color: '#e8f4f8', fontSize: 16 }}
          />
          <Dropdown menu={userMenu} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#00d4ff' }} />
              <span style={{ color: '#e8f4f8' }}>{user?.username}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content
          style={{
            margin: 24,
            background: 'transparent',
            minHeight: 'calc(100vh - 104px)',
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
`

### 5.2 LoginLayout (登录页布局)

`	ypescript
// src/layouts/LoginLayout.tsx
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
      <div style={{ position: 'relative', zIndex: 1, width: '100%', maxWidth: 440 }}>
        {children}
      </div>
    </div>
  )
}
`

## 6. 全局交互与 UX 规范

### 6.1 加载状态

| 场景 | 表现 |
|------|------|
| 页面首次加载 | 骨架屏 (Skeleton) |
| 表格数据加载 | ProTable 自带 loading |
| 表单提交 | Button loading 态 |
| 文件上传 | 进度条 + 百分比 |
| 对话发送 | 输入框禁用 + 发送按钮 loading |
| 全局错误 | Toast 提示 + 错误页 |

### 6.2 错误处理

`	ypescript
// 全局错误边界
class ErrorBoundary extends React.Component {
  state = { hasError: false, error: null }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <ExclamationCircleOutlined style={{ fontSize: 48, color: '#ff6b6b' }} />
          <h2>出错了</h2>
          <p>{this.state.error?.message}</p>
          <Button onClick={() => window.location.reload()}>刷新页面</Button>
        </div>
      )
    }
    return this.props.children
  }
}
`

### 6.3 Toast 提示

统一使用 Ant Design message:
`	ypescript
message.success('操作成功')
message.error('操作失败: ' + errorMsg)
message.warning('警告信息')
message.info('提示信息')
`

### 6.4 确认对话框

危险操作使用 Modal.confirm:
`	ypescript
Modal.confirm({
  title: '确认删除?',
  content: '删除后无法恢复',
  okText: '删除',
  okType: 'danger',
  cancelText: '取消',
  onOk: () => deleteAgent(id),
})
`

### 6.5 表单校验

统一使用 Ant Design Form 校验规则:
`	ypescript
<Form rules={[
  { required: true, message: '请输入名称' },
  { max: 120, message: '名称不能超过 120 字符' },
]}>
`

### 6.6 响应式行为

| 屏幕宽度 | 行为 |
|----------|------|
| >= 1280px | 正常侧边栏展开 |
| < 1280px | 侧边栏自动折叠 |
| < 768px | 不推荐使用 (管理后台) |

---

## 7. 文件上传详细设计

### 7.1 上传流程

`
用户选择文件
    │
    ▼
[前端校验] 文件大小 ≤ 50MB? 类型在白名单?
    │ 否 → 显示错误 Toast
    │ 是
    ▼
[构建 FormData] file + folder_id
    │
    ▼
[POST /knowledge-bases/:id/upload]
    │
    ▼
[后端处理]
  1. 保存文件到 uploads/
  2. 创建 KBDocument 记录 (status=pending)
  3. 异步触发 process_document
    │
    ▼
[返回 document_id]
    │
    ▼
[前端轮询] GET /knowledge-bases/:id/documents
  每 2 秒查询一次, 直到 status 为 ready/failed
    │
    ▼
[更新 UI]
  ready → 绿色 ✅ + 显示分块数
  failed → 红色 ❌ + 显示错误信息
`

### 7.2 文件类型白名单

| 扩展名 | 类型 | 解析器 |
|--------|------|--------|
| .pdf | pdf | pdfminer / pypdf |
| .docx | docx | python-docx |
| .txt | txt | 直接读取 |
| .md | markdown | 直接读取 |
| .csv | csv | 直接读取 |
| .json | json | 直接读取 |
| .py, .js, .ts, .jsx, .tsx | code | 直接读取 |
| .java, .go, .rs, .c, .cpp | code | 直接读取 |
| .yaml, .yml, .toml | code | 直接读取 |

### 7.3 上传组件交互

`
┌──────────────────────────────────────────┐
│  📤 拖拽文件到此处 或 点击选择文件        │
│                                          │
│  支持: PDF, DOCX, TXT, MD, Code         │
│  单文件最大 50MB, 最多 10 个文件         │
└──────────────────────────────────────────┘

已选文件列表:
┌──────────────────────────────────────────┐
│ 📄 api_spec.pdf        2.3 MB   [取消]   │
│ 📄 guide.docx          156 KB   [取消]   │
│ 📄 readme.md            12 KB   [取消]   │
└──────────────────────────────────────────┘

目标文件夹: [📁 产品 ▾]
                              [开始上传]
`

## 8. 开发实施指南

### 8.1 开发顺序 (与 PRD 一致)

**Phase 1: 基础设施 + 主题系统**
`ash
# 1. 初始化前端项目
cd web
rm -rf src/*  # 清空旧代码
npm init -y
npm install react react-dom
npx vite@latest . --template react-ts

# 2. 安装核心依赖
npm install antd @ant-design/pro-components react-router-dom axios zustand framer-motion echarts-for-react lucide-react

# 3. 创建目录结构
mkdir -p src/{assets/{icons},components/{IceCrystalCard,GlassButton,ParticleBg},layouts,pages/{Login,Dashboard,AgentList,AgentDetail,KnowledgeBase,UserManagement,MCPManagement,SkillManagement,Settings},services,stores,utils,styles}

# 4. 创建全局样式
echo ":root { --ice-primary: #00d4ff; ... }" > src/styles/variables.css

# 5. 创建入口文件
# - src/main.tsx (ConfigProvider + BrowserRouter)
# - src/App.tsx (路由配置)
`

**Phase 2-7: 按页面逐个开发**

每个页面的开发顺序:
1. 先写 API 服务函数 (src/services/)
2. 再写页面组件 (src/pages/)
3. 最后联调测试

### 8.2 后端 RAG 增强实施

`ash
# 1. 安装新依赖
pip install sentence-transformers numpy

# 2. 修改模型
# - app/models.py: 添加 KBFeedback, RetrievalLog, rag_config

# 3. 修改服务
# - app/services.py: 添加 QueryRewriter, HybridRetriever, ContextBuilder

# 4. 修改 Agent
# - app/agent.py: 集成 RAG 检索链路

# 5. 修改 API
# - app/api.py: 新增检索/反馈/统计接口

# 6. 修改 Schema
# - app/schemas.py: 新增 RAGConfigUpdate, RetrievalFeedbackRequest

# 7. 修改 Prompt
# - app/services.py: 替换 DEFAULT_SYSTEM_PROMPT 为 RAG_SYSTEM_PROMPT
`

### 8.3 关键文件清单

**前端新增/修改文件 (约 25 个)**:
`
web/src/styles/variables.css              (新建)
web/src/App.tsx                            (新建/重写)
web/src/main.tsx                           (新建/重写)
web/src/layouts/BasicLayout.tsx            (新建)
web/src/layouts/LoginLayout.tsx            (新建)
web/src/components/IceCrystalCard/index.tsx (新建)
web/src/components/GlassButton/index.tsx   (新建)
web/src/components/ParticleBg/index.tsx    (新建)
web/src/stores/auth.ts                     (新建)
web/src/stores/layout.ts                   (新建)
web/src/services/request.ts                (新建)
web/src/services/agent.ts                  (新建)
web/src/services/knowledgeBase.ts          (新建)
web/src/services/user.ts                   (新建)
web/src/services/mcp.ts                    (新建)
web/src/services/skill.ts                  (新建)
web/src/services/settings.ts               (新建)
web/src/pages/Login/index.tsx              (新建)
web/src/pages/Dashboard/index.tsx          (新建)
web/src/pages/AgentList/index.tsx          (新建)
web/src/pages/AgentList/AgentDrawer.tsx    (新建)
web/src/pages/AgentDetail/index.tsx        (新建)
web/src/pages/AgentDetail/TestChat.tsx     (新建)
web/src/pages/KnowledgeBase/index.tsx      (新建)
web/src/pages/KnowledgeBase/KBDetail.tsx   (新建)
web/src/pages/KnowledgeBase/FolderTree.tsx (新建)
web/src/pages/KnowledgeBase/FileUpload.tsx (新建)
web/src/pages/KnowledgeBase/KBSearch.tsx   (新建)
web/src/pages/UserManagement/index.tsx     (新建)
web/src/pages/MCPManagement/index.tsx      (新建)
web/src/pages/SkillManagement/index.tsx    (新建)
web/src/pages/Settings/index.tsx           (新建)
web/tsconfig.json                          (新建)
web/package.json                           (重写)
`

**后端修改文件 (约 6 个)**:
`
app/models.py              (新增: KBFeedback, RetrievalLog, rag_config)
app/schemas.py             (新增: RAGConfigUpdate, RetrievalFeedbackRequest)
app/services.py            (新增: QueryRewriter, HybridRetriever, ContextBuilder, RAG_PROMPT)
app/agent.py               (修改: ask_agent 集成 RAG)
app/tools.py               (修改: search_knowledge_base 改用混合检索)
app/api.py                 (新增: /retrieval-feedback, /knowledge-bases/:id/stats)
requirements.txt           (新增: sentence-transformers, numpy)
`

## 9. 验收 Checklist

### 9.1 前端验收

- [ ] IceCrystalCard 组件: hover 时发光/倾斜/悬浮效果正常
- [ ] GlassButton 组件: 4 种 variant + loading 态 + 光泽扫过动画
- [ ] ParticleBg 组件: Canvas 粒子流畅 (≥ 55fps)
- [ ] BasicLayout: 侧边栏可折叠, 菜单高亮正确
- [ ] LoginLayout: 居中卡片 + 粒子背景
- [ ] 登录/注册: 表单校验 + 错误提示 + 跳转
- [ ] 仪表盘: 4 个统计卡片 + 趋势图 + 快捷操作 + 活动列表
- [ ] Agent 列表: ProTable 渲染 + 搜索筛选 + 分页
- [ ] Agent Drawer: 表单校验 + 知识库多选 + 保存/取消
- [ ] Agent 详情: 双栏布局 + 对话测试 + Markdown 渲染
- [ ] KB 列表: ProCard 网格 + 状态标签
- [ ] KB 详情: 文件夹树 + 文档表格 + Tab 切换
- [ ] 文件上传: 拖拽 + 多选 + 进度显示
- [ ] 检索测试: 输入问题 + 显示结果 + 来源标注 + 反馈按钮
- [ ] 用户管理: 列表 + 角色标签 + 启用/禁用
- [ ] MCP 管理: 列表 + 新建/编辑
- [ ] Skill 管理: 列表 + 新建/编辑
- [ ] 系统设置: KV 表格 + 编辑/删除
- [ ] 全局错误边界: 异常时显示错误页
- [ ] Token 过期: 自动跳转登录

### 9.2 后端验收

- [ ] 混合检索: 向量 + 关键词 RRF 融合
- [ ] MMR 去重: 结果多样性
- [ ] Cross-Encoder 重排: bge-reranker-base
- [ ] ContextBuilder: 来源标注 + token 截断
- [ ] RAG Prompt: 引用来源 + 不知道就说不知道
- [ ] 检索日志: 记录每次检索
- [ ] 用户反馈: 点赞/踩存储
- [ ] KB 统计: 文档数/分块数/热门检索词
- [ ] 文件上传: 类型校验 + 大小限制
- [ ] 文档处理: 分块 + 向量化 + 状态更新
- [ ] Agent 对话集成 RAG: 自动检索 + 注入上下文

### 9.3 性能验收

- [ ] 首屏加载 < 2s
- [ ] 页面切换 < 300ms
- [ ] API 响应 < 500ms (不含 LLM)
- [ ] 向量检索 < 200ms
- [ ] RAG 完整链路 < 3s
- [ ] 粒子背景 ≥ 55fps

---

## 10. 附录

### 10.1 相关文档

- [PRD.md](./PRD.md) - 产品需求文档
- [TASKS.md](./TASKS.md) - 任务清单 (历史)
- [README.md](./README.md) - 项目说明

### 10.2 术语表

| 术语 | 说明 |
|------|------|
| RAG | Retrieval-Augmented Generation, 检索增强生成 |
| KB | Knowledge Base, 知识库 |
| KBChunk | 知识库分块 |
| Embedding | 文本向量化表示 |
| ChromaDB | 本地向量数据库 |
| Cross-Encoder | 交叉编码器, 用于重排序 |
| MMR | Maximal Marginal Relevance, 最大边际相关性 |
| RRF | Reciprocal Rank Fusion, 倒数排名融合 |
| MCP | Model Context Protocol |
| SSE | Server-Sent Events, 服务端推送 |

---

*本文档结束。*
