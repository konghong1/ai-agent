import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot,
  BrainCircuit,
  Cable,
  KeyRound,
  LogOut,
  MessageSquare,
  Palette,
  Plus,
  RefreshCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Wrench
} from "lucide-react";
import "./styles.css";
import { MessageRenderer } from './components';

const TOKEN_KEY = "agent-platform-token";

const THEME_KEY = "agent-platform-theme";
const THEMES = [
  { id: "dark", label: "暗黑默认", icon: "🌑" },
  { id: "ice", label: "冰晶色", icon: "❄️" },
  { id: "planet", label: "悬浮星体", icon: "🪐" }
];

function authHeaders(token) {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`
  };
}

async function api(path, { token, method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    headers: token ? authHeaders(token) : { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    throw new Error(data?.detail || "请求失败");
  }
  return data;
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || "");
  const [user, setUser] = useState(null);
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ email: "", username: "", password: "" });
  const [agents, setAgents] = useState([]);
  const [activeAgentId, setActiveAgentId] = useState(null);
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("ready");
  const [error, setError] = useState("");
  const [view, setView] = useState("chat");
  const [mcpServers, setMcpServers] = useState([]);
  const [skills, setSkills] = useState([]);
  const [agentDraft, setAgentDraft] = useState({ name: "New Agent", description: "", system_prompt: "", model_name: "", temperature: 0 });
  const [mcpDraft, setMcpDraft] = useState({ name: "filesystem", transport: "stdio", command: "npx", args: "-y @modelcontextprotocol/server-filesystem D:/workspace", url: "" });
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || "dark");
  const [skillDraft, setSkillDraft] = useState({ name: "code-review", title: "代码审查", description: "审查代码风险、可维护性和测试缺口", path: "skills/code-review" });

  const activeAgent = useMemo(() => agents.find((agent) => agent.id === Number(activeAgentId)) || agents[0], [agents, activeAgentId]);

  useEffect(() => {
    if (!token) return;
    bootstrap();
  }, [token]);

  useEffect(() => {
    if (!token || !activeAgent) return;
    loadThreads(activeAgent.id);
  }, [token, activeAgent?.id]);


  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  async function bootstrap() {
    try {
      setError("");
      const me = await api("/auth/me", { token });
      setUser(me);
      const nextAgents = await api("/agents", { token });
      setAgents(nextAgents);
      setActiveAgentId((current) => current || nextAgents[0]?.id || null);
      setMcpServers(await api("/mcp-servers", { token }));
      setSkills(await api("/skills", { token }));
    } catch (err) {
      logout();
      setError(err.message);
    }
  }

  async function loadThreads(agentId) {
    const nextThreads = await api(`/threads?agent_id=${agentId}`, { token });
    setThreads(nextThreads);
    if (nextThreads.length) {
      setActiveThreadId(nextThreads[0].id);
      setMessages(await api(`/threads/${nextThreads[0].id}/messages`, { token }));
    } else {
      setActiveThreadId(null);
      setMessages([]);
    }
  }

  async function handleAuth(event) {
    event.preventDefault();
    setStatus("thinking");
    setError("");
    try {
      const path = authMode === "login" ? "/auth/login" : "/auth/register";
      const payload = authMode === "login" ? { email: authForm.email, password: authForm.password } : authForm;
      const data = await api(path, { method: "POST", body: payload });
      localStorage.setItem(TOKEN_KEY, data.access_token);
      setToken(data.access_token);
      setUser(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus("ready");
    }
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
    setAgents([]);
    setThreads([]);
    setMessages([]);
  }


  // Handle choice button click from AI messages
  async function handleChoice(value, label) {
    if (status === "thinking") return;
    const message = label || value;
    setInput("");
    setError("");
    setStatus("thinking");
    setMessages((current) => [...current, { role: "user", content: message, id: `local-${Date.now()}` }]);
    try {
      const data = await api("/chat", {
        token,
        method: "POST",
        body: { message, agent_id: activeAgent.id, thread_id: activeThreadId }
      });
      setActiveThreadId(data.thread_id);
      setMessages(await api(`/threads/${data.thread_id}/messages`, { token }));
      setThreads(await api(`/threads?agent_id=${activeAgent.id}`, { token }));
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus("ready");
    }
  }

  async function sendMessage(event) {
    event?.preventDefault();
    const message = input.trim();
    if (!message || !activeAgent || status === "thinking") return;
    setInput("");
    setError("");
    setStatus("thinking");
    setMessages((current) => [...current, { role: "user", content: message, id: `local-${Date.now()}` }]);
    try {
      const data = await api("/chat", {
        token,
        method: "POST",
        body: { message, agent_id: activeAgent.id, thread_id: activeThreadId }
      });
      setActiveThreadId(data.thread_id);
      setMessages(await api(`/threads/${data.thread_id}/messages`, { token }));
      setThreads(await api(`/threads?agent_id=${activeAgent.id}`, { token }));
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus("ready");
    }
  }

  async function createAgent(event) {
    event.preventDefault();
    const body = {
      ...agentDraft,
      system_prompt: agentDraft.system_prompt || undefined,
      model_name: agentDraft.model_name || undefined,
      temperature: Number(agentDraft.temperature || 0)
    };
    const created = await api("/agents", { token, method: "POST", body });
    const nextAgents = await api("/agents", { token });
    setAgents(nextAgents);
    setActiveAgentId(created.id);
    setView("chat");
  }

  async function createThread() {
    if (!activeAgent) return;
    const thread = await api("/threads", { token, method: "POST", body: { agent_id: activeAgent.id, title: "New chat" } });
    setActiveThreadId(thread.id);
    setMessages([]);
    setThreads(await api(`/threads?agent_id=${activeAgent.id}`, { token }));
  }

  async function createMcp(event) {
    event.preventDefault();
    const body = {
      ...mcpDraft,
      args: mcpDraft.args.split(" ").map((item) => item.trim()).filter(Boolean),
      env: {}
    };
    await api("/mcp-servers", { token, method: "POST", body });
    setMcpServers(await api("/mcp-servers", { token }));
  }

  async function createSkill(event) {
    event.preventDefault();
    await api("/skills", { token, method: "POST", body: { ...skillDraft, source_type: "local" } });
    setSkills(await api("/skills", { token }));
  }

  if (!token || !user) {
    return (
      <main className="auth-shell">
        <section className="auth-panel">
          <div className="brand-lockup">
            <div className="brand-mark"><Bot size={24} /></div>
            <div>
              <p className="eyebrow">AI Agent Platform</p>
              <h1>{authMode === "login" ? "登录控制台" : "创建账号"}</h1>
            </div>
          </div>
          <form className="stack-form" onSubmit={handleAuth}>
            <label>邮箱<input value={authForm.email} onChange={(event) => setAuthForm({ ...authForm, email: event.target.value })} type="email" required /></label>
            {authMode === "register" && (
              <label>用户名<input value={authForm.username} onChange={(event) => setAuthForm({ ...authForm, username: event.target.value })} required /></label>
            )}
            <label>密码<input value={authForm.password} onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })} type="password" minLength={6} required /></label>
            {error && <div className="error-strip">{error}</div>}
            <button className="primary-button" disabled={status === "thinking"}><KeyRound size={18} />{authMode === "login" ? "登录" : "注册"}</button>
          </form>
          <button className="text-button" onClick={() => setAuthMode(authMode === "login" ? "register" : "login")}>
            {authMode === "login" ? "没有账号？注册一个" : "已有账号？去登录"}
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="shell" data-theme={theme}>
      <aside className="left-panel">
        <div className="brand-lockup">
          <div className="brand-mark"><Bot size={24} /></div>
          <div>
            <p className="eyebrow">Signed in as {user.username}</p>
            <h1>Agent Console</h1>
          </div>
        </div>

        <div className="nav-list">
          <button className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}><MessageSquare size={17} />聊天</button>
          <button className={view === "agents" ? "active" : ""} onClick={() => setView("agents")}><BrainCircuit size={17} />Agent</button>
          <button className={view === "mcp" ? "active" : ""} onClick={() => setView("mcp")}><Cable size={17} />MCP</button>
          <button className={view === "skills" ? "active" : ""} onClick={() => setView("skills")}><Sparkles size={17} />Skill</button>
        </div>

        <label className="select-label">当前 Agent
          <select value={activeAgent?.id || ""} onChange={(event) => setActiveAgentId(Number(event.target.value))}>
            {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
          </select>
        </label>

        <div className="history-list">
          <div className="section-title"><MessageSquare size={16} /><span>会话</span><button onClick={createThread} title="新会话"><Plus size={15} /></button></div>
          {threads.map((thread) => (
            <button className={`history-row ${thread.id === activeThreadId ? "active" : ""}`} key={thread.id} onClick={async () => {
              setActiveThreadId(thread.id);
              setMessages(await api(`/threads/${thread.id}/messages`, { token }));
            }}>
              <span>{thread.title}</span>
              <small>{new Date(thread.updated_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</small>
            </button>
          ))}
        </div>

        <button className="secondary-button" onClick={bootstrap}><RefreshCcw size={16} />刷新</button>
        <button className="secondary-button" onClick={logout}><LogOut size={16} />退出</button>
      </aside>

      <section className="chat-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">{activeAgent?.model_name || "No model"}</p>
            <h2>{viewTitle(view, activeAgent)}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div className="theme-switcher">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  className={`theme-btn ${theme === t.id ? "active" : ""}`}
                  onClick={() => setTheme(t.id)}
                  title={t.label}
                  type="button"
                >
                  {t.icon}
                </button>
              ))}
            </div>
            <div className="status-pill"><ShieldCheck size={16} />{status === "thinking" ? "运行中" : "已连接"}</div>
          </div>
        </header>

        {view === "chat" && (
          <>
            <div className="chat-stream" aria-live="polite">
              {messages.length === 0 && <div className="empty-state"><Wrench size={28} />选择一个 Agent，开始第一轮对话。</div>}
              {messages.map((message) => (
                <article className={`message ${message.role}`} key={message.id}>
                  <div className="avatar">{message.role === "assistant" ? <Sparkles size={17} /> : "你"}</div>
                  <MessageRenderer message={message} onChoiceClick={handleChoice} />
                </article>
              ))}
              {status === "thinking" && <article className="message assistant"><div className="avatar"><Sparkles size={17} /></div><div className="bubble typing"><span /><span /><span /></div></article>}
            </div>
            {error && <div className="error-strip">{error}</div>}
            <form className="composer" onSubmit={sendMessage}>
              <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="给 Agent 发送消息..." rows={1} />
              <button type="submit" disabled={!input.trim() || status === "thinking"} aria-label="发送"><Send size={20} /></button>
            </form>
          </>
        )}

        {view === "agents" && (
          <ConfigView title="创建 Agent" onSubmit={createAgent}>
            <label>名称<input value={agentDraft.name} onChange={(event) => setAgentDraft({ ...agentDraft, name: event.target.value })} /></label>
            <label>描述<input value={agentDraft.description} onChange={(event) => setAgentDraft({ ...agentDraft, description: event.target.value })} /></label>
            <label>模型<input value={agentDraft.model_name} onChange={(event) => setAgentDraft({ ...agentDraft, model_name: event.target.value })} placeholder={activeAgent?.model_name} /></label>
            <label>系统提示词<textarea value={agentDraft.system_prompt} onChange={(event) => setAgentDraft({ ...agentDraft, system_prompt: event.target.value })} rows={5} /></label>
            <button className="primary-button"><Plus size={18} />创建 Agent</button>
            <ItemList items={agents} empty="还没有 Agent" />
          </ConfigView>
        )}

        {view === "mcp" && (
          <ConfigView title="配置 MCP Server" onSubmit={createMcp}>
            <label>名称<input value={mcpDraft.name} onChange={(event) => setMcpDraft({ ...mcpDraft, name: event.target.value })} /></label>
            <label>Transport<select value={mcpDraft.transport} onChange={(event) => setMcpDraft({ ...mcpDraft, transport: event.target.value })}><option value="stdio">stdio</option><option value="sse">sse</option><option value="http">http</option></select></label>
            <label>Command<input value={mcpDraft.command} onChange={(event) => setMcpDraft({ ...mcpDraft, command: event.target.value })} /></label>
            <label>Args<input value={mcpDraft.args} onChange={(event) => setMcpDraft({ ...mcpDraft, args: event.target.value })} /></label>
            <label>URL<input value={mcpDraft.url} onChange={(event) => setMcpDraft({ ...mcpDraft, url: event.target.value })} /></label>
            <button className="primary-button"><Plus size={18} />保存 MCP</button>
            <ItemList items={mcpServers} empty="还没有 MCP Server" />
          </ConfigView>
        )}

        {view === "skills" && (
          <ConfigView title="登记 Skill" onSubmit={createSkill}>
            <label>名称<input value={skillDraft.name} onChange={(event) => setSkillDraft({ ...skillDraft, name: event.target.value })} /></label>
            <label>标题<input value={skillDraft.title} onChange={(event) => setSkillDraft({ ...skillDraft, title: event.target.value })} /></label>
            <label>描述<input value={skillDraft.description} onChange={(event) => setSkillDraft({ ...skillDraft, description: event.target.value })} /></label>
            <label>路径<input value={skillDraft.path} onChange={(event) => setSkillDraft({ ...skillDraft, path: event.target.value })} /></label>
            <button className="primary-button"><Plus size={18} />保存 Skill</button>
            <ItemList items={skills} empty="还没有 Skill" />
          </ConfigView>
        )}
      </section>
    </main>
  );
}

function viewTitle(view, activeAgent) {
  if (view === "agents") return "Agent 配置";
  if (view === "mcp") return "MCP 配置";
  if (view === "skills") return "Skill 管理";
  return activeAgent?.name || "Agent Chat";
}

function ConfigView({ title, onSubmit, children }) {
  return (
    <div className="config-view">
      <form className="config-form" onSubmit={onSubmit}>
        <h3>{title}</h3>
        {children}
      </form>
    </div>
  );
}

function ItemList({ items, empty }) {
  return (
    <div className="item-list">
      {items.length === 0 && <p className="muted">{empty}</p>}
      {items.map((item) => (
        <div className="item-row" key={item.id}>
          <strong>{item.title || item.name}</strong>
          <span>{item.description || item.transport || item.model_name || item.path}</span>
        </div>
      ))}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
