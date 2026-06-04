import React, { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Bot,
  BrainCircuit,
  Calculator,
  Clock3,
  FileSearch,
  Gauge,
  Github,
  History,
  Network,
  Palette,
  RotateCcw,
  Send,
  Sparkles,
  TerminalSquare,
  Wrench
} from "lucide-react";
import "./styles.css";

const starterMessages = [
  {
    role: "assistant",
    content:
      "你好，我是本地 LangChain Agent。可以调用时间、计算器、工作区文件等工具，并把调用链记录到 LangSmith。"
  }
];

const STORAGE_KEY = "agent-console-sessions";
const THEME_KEY = "agent-console-theme";

function createSession(title = "新的会话") {
  return {
    id: `local-${crypto.randomUUID().slice(0, 8)}`,
    title,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messages: starterMessages
  };
}

function loadSessions() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (Array.isArray(saved) && saved.length) return saved;
  } catch {
    // Ignore invalid local data and start clean.
  }
  return [createSession("本地调试")];
}

const quickPrompts = [
  "现在几点？用工具计算 23*19",
  "列出当前项目文件",
  "读取 README.md，总结如何启动",
  "解释一下这个 Agent 的调用链路"
];

const tools = [
  { name: "current_time", icon: Clock3, accent: "mint" },
  { name: "calculator", icon: Calculator, accent: "amber" },
  { name: "list_workspace_files", icon: FileSearch, accent: "cyan" },
  { name: "read_workspace_text_file", icon: TerminalSquare, accent: "rose" }
];

function App() {
  const [sessions, setSessions] = useState(loadSessions);
  const [activeSessionId, setActiveSessionId] = useState(() => sessions[0]?.id);
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || "dark");
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("ready");
  const [lastError, setLastError] = useState("");
  const inputRef = useRef(null);

  const activeSession = sessions.find((session) => session.id === activeSessionId) || sessions[0];
  const messages = activeSession?.messages || starterMessages;
  const threadId = activeSession?.id || "local-debug";

  const stats = useMemo(() => {
    const userCount = messages.filter((message) => message.role === "user").length;
    return {
      turns: userCount,
      traces: userCount,
      thread: threadId
    };
  }, [messages, threadId]);

  React.useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions]);

  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  function updateActiveSession(updater) {
    setSessions((current) =>
      current.map((session) => {
        if (session.id !== activeSessionId) return session;
        const nextSession = updater(session);
        return { ...nextSession, updatedAt: new Date().toISOString() };
      })
    );
  }

  async function sendMessage(text = input) {
    const message = text.trim();
    if (!message || status === "thinking") return;

    setInput("");
    setLastError("");
    setStatus("thinking");
    updateActiveSession((session) => ({
      ...session,
      title: session.title === "新的会话" || session.title === "本地调试" ? message.slice(0, 24) : session.title,
      messages: [...session.messages, { role: "user", content: message }]
    }));

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json; charset=utf-8" },
        body: JSON.stringify({ message, thread_id: threadId })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Agent request failed.");
      }
      updateActiveSession((session) => ({
        ...session,
        id: data.thread_id || session.id,
        messages: [...session.messages, { role: "assistant", content: data.answer }]
      }));
      if (data.thread_id && data.thread_id !== activeSessionId) {
        setActiveSessionId(data.thread_id);
      }
      setStatus("ready");
    } catch (error) {
      setLastError(error.message);
      updateActiveSession((session) => ({
        ...session,
        messages: [...session.messages, { role: "assistant", content: `请求失败：${error.message}` }]
      }));
      setStatus("error");
    } finally {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  function resetChat() {
    const session = createSession();
    setSessions((current) => [session, ...current]);
    setActiveSessionId(session.id);
    setLastError("");
    setStatus("ready");
  }

  function switchSession(sessionId) {
    setActiveSessionId(sessionId);
    setLastError("");
    setStatus("ready");
  }

  function cycleTheme() {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }

  function handleSubmit(event) {
    event.preventDefault();
    sendMessage();
  }

  return (
    <main className="shell">
      <section className="left-panel">
        <div className="brand-lockup">
          <div className="brand-mark">
            <Bot size={24} />
          </div>
          <div>
            <p className="eyebrow">LangChain</p>
            <h1>Agent Console</h1>
          </div>
        </div>

        <div className="agent-core">
          <div className={`core-ring ${status}`}>
            <BrainCircuit size={48} />
            <span />
            <span />
          </div>
          <div className="core-copy">
            <p>Runtime</p>
            <strong>{status === "thinking" ? "Thinking" : status === "error" ? "Alert" : "Online"}</strong>
          </div>
        </div>

        <div className="metric-grid">
          <Metric icon={Activity} label="Turns" value={stats.turns} />
          <Metric icon={Network} label="Trace" value={stats.traces} />
          <Metric icon={Gauge} label="Port" value="8010" />
        </div>

        <div className="history-list">
          <div className="section-title">
            <History size={16} />
            <span>History</span>
          </div>
          {sessions.slice(0, 8).map((session) => (
            <button
              className={`history-row ${session.id === activeSessionId ? "active" : ""}`}
              key={session.id}
              onClick={() => switchSession(session.id)}
            >
              <span>{session.title}</span>
              <small>{new Date(session.updatedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</small>
            </button>
          ))}
        </div>

        <div className="tool-list">
          <div className="section-title">
            <Wrench size={16} />
            <span>Tools</span>
          </div>
          {tools.map((tool) => (
            <div className="tool-row" key={tool.name}>
              <div className={`tool-icon ${tool.accent}`}>
                <tool.icon size={17} />
              </div>
              <span>{tool.name}</span>
              <i />
            </div>
          ))}
        </div>
      </section>

      <section className="chat-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">Thread</p>
            <h2>{threadId}</h2>
          </div>
          <div className="top-actions">
            <a
              className="icon-button"
              href="https://smith.langchain.com"
              target="_blank"
              rel="noreferrer"
              title="打开 LangSmith"
              aria-label="打开 LangSmith"
            >
              <Github size={18} />
            </a>
            <button className="icon-button" onClick={cycleTheme} title="切换主题" aria-label="切换主题">
              <Palette size={18} />
            </button>
            <button className="icon-button" onClick={resetChat} title="新会话" aria-label="新会话">
              <RotateCcw size={18} />
            </button>
          </div>
        </header>

        <div className="chat-stream" aria-live="polite">
          {messages.map((message, index) => (
            <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
              <div className="avatar">{message.role === "assistant" ? <Sparkles size={17} /> : "你"}</div>
              <div className="bubble">{message.content}</div>
            </article>
          ))}
          {status === "thinking" && (
            <article className="message assistant">
              <div className="avatar">
                <Sparkles size={17} />
              </div>
              <div className="bubble typing">
                <span />
                <span />
                <span />
              </div>
            </article>
          )}
        </div>

        <div className="quick-row">
          {quickPrompts.map((prompt) => (
            <button key={prompt} onClick={() => sendMessage(prompt)} disabled={status === "thinking"}>
              {prompt}
            </button>
          ))}
        </div>

        {lastError && <div className="error-strip">{lastError}</div>}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
            placeholder="问 Agent 一个问题..."
            rows={1}
          />
          <button type="submit" disabled={!input.trim() || status === "thinking"} aria-label="发送">
            <Send size={20} />
          </button>
        </form>
      </section>
    </main>
  );
}

function Metric({ icon: Icon, label, value }) {
  return (
    <div className="metric">
      <Icon size={17} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
