import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot, BrainCircuit, Cable, ChevronDown, ChevronRight, Database,
  KeyRound, Library, LogOut, MessageSquare, Palette, Plus, RefreshCcw,
  Send, ShieldCheck, Sparkles, Trash2, Upload, Users, Settings, Wrench
} from "lucide-react";
import "./styles.css";
import { MessageRenderer } from './components';

const TOKEN_KEY = "agent-platform-token";
const THEME_KEY = "agent-platform-theme";
const THEMES = [
  { id: "dark", label: "暗黑默认", icon: "\ud83c\udf11" },
  { id: "ice", label: "冰晶色", icon: "\u2744\ufe0f" },
  { id: "planet", label: "悬浮星体", icon: "\ud83c\udf10" }
];

function authHeaders(token) {
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

async function api(path, { token, method = "GET", body } = {}) {
  const response = await fetch(path, {
    method, headers: token ? authHeaders(token) : { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) { throw new Error(data?.detail || "Request failed"); }
  return data;
}

function TreeNode({ node, depth = 0, expandedIds, onToggle, onSelect, selectedId }) {
  const isExpanded = expandedIds.has(node.id);
  const isSelected = selectedId === node.id;
  return (
    <div>
      <div className="tree-node" style={{ paddingLeft: depth * 20 + 8 }}
           onClick={() => onSelect && onSelect(node.id)}>
        <button className="tree-toggle"
          onClick={(e) => { e.stopPropagation(); onToggle(node.id); }}
          style={{ visibility: node.children.length ? "visible" : "hidden" }}>
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <Library size={14} style={{ marginRight: 6, color: isSelected ? "#5de2b9" : "#9ea49b" }} />
        <span style={{ fontWeight: isSelected ? 700 : 400 }}>{node.name}</span>
        {node.document_count > 0 && (
          <span style={{ marginLeft: 6, fontSize: 11, color: "#6a7098" }}>({node.document_count})</span>
        )}
      </div>
      {isExpanded && node.children.map(child => (
        <TreeNode key={child.id} node={child} depth={depth + 1} expandedIds={expandedIds}
          onToggle={onToggle} onSelect={onSelect} selectedId={selectedId} />
      ))}
    </div>
  );
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
  const [knowledgeBases, setKnowledgeBases] = useState([]);
  const [activeKbId, setActiveKbId] = useState(null);
  const [kbDraft, setKbDraft] = useState({ name: "My KB", description: "", embedding_model: "text-embedding-3-small", chunk_size: 500, chunk_overlap: 50 });
  const [folderTree, setFolderTree] = useState([]);
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [selectedFolderId, setSelectedFolderId] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [users, setUsers] = useState([]);
  const [settings, setSettings] = useState([]);
  const [settingKey, setSettingKey] = useState("");
  const [settingValue, setSettingValue] = useState("");
  const activeAgent = useMemo(() => agents.find((agent) => agent.id === Number(activeAgentId)) || agents[0], [agents, activeAgentId]);
  useEffect(() => { if (!token) return; bootstrap(); }, [token]);
  useEffect(() => { if (!token || !activeAgent) return; loadThreads(activeAgent.id); }, [token, activeAgent?.id]);
  useEffect(() => { document.documentElement.setAttribute("data-theme", theme); localStorage.setItem(THEME_KEY, theme); }, [theme]);
  useEffect(() => { if (view === "knowledge" && token && activeAgent) loadKnowledgeBases(); }, [view, token, activeAgentId]);
  useEffect(() => { if (view === "users" && token) loadUsers(); }, [view, token]);
  useEffect(() => { if (view === "settings" && token) loadSettings(); }, [view, token]);
  useEffect(() => { if (activeKbId) { loadFolderTree(); loadDocuments(); } }, [activeKbId]);

  async function bootstrap() {
    try { setError(""); setUser(await api("/auth/me", { token }));
      const nextAgents = await api("/agents", { token }); setAgents(nextAgents);
      setActiveAgentId(c => c || nextAgents[0]?.id || null);
      setMcpServers(await api("/mcp-servers", { token })); setSkills(await api("/skills", { token }));
    } catch (err) { logout(); setError(err.message); }
  }
  async function loadThreads(agentId) {
    const nt = await api(`/threads?agent_id=${agentId}`, { token }); setThreads(nt);
    if (nt.length) { setActiveThreadId(nt[0].id); setMessages(await api(`/threads/${nt[0].id}/messages`, { token })); }
    else { setActiveThreadId(null); setMessages([]); }
  }
  async function loadThreadMessages(threadId) { setActiveThreadId(threadId); setMessages(await api(`/threads/${threadId}/messages`, { token })); }

  async function loadKnowledgeBases() {
    try { const kbs = await api("/knowledge-bases", { token }); setKnowledgeBases(kbs); if (kbs.length && !activeKbId) setActiveKbId(kbs[0].id); }
    catch (err) { setError(err.message); }
  }
  async function createKnowledgeBase() {
    try { const kb = await api("/knowledge-bases", { token, method: "POST", body: kbDraft }); setKnowledgeBases(p => [...p, kb]); setActiveKbId(kb.id);
      setKbDraft({ name: "My KB", description: "", embedding_model: "text-embedding-3-small", chunk_size: 500, chunk_overlap: 50 });
    } catch (err) { setError(err.message); }
  }
  async function deleteKnowledgeBase(kbId) {
    try { await api(`/knowledge-bases/${kbId}`, { token, method: "DELETE" }); setKnowledgeBases(p => p.filter(k => k.id !== kbId)); if (activeKbId === kbId) setActiveKbId(null); }
    catch (err) { setError(err.message); }
  }
  async function createFolder(parentId = null) {
    const name = prompt(parentId ? "子文件夹名称:" : "文件夹名称:"); if (!name) return;
    try { const folder = await api(`/knowledge-bases/${activeKbId}/folders`, { token, method: "POST", body: { name, parent_id: parentId } }); await loadFolderTree(); setExpandedFolders(p => new Set([...p, folder.id])); }
    catch (err) { setError(err.message); }
  }
  async function loadFolderTree() { if (!activeKbId) return; try { setFolderTree(await api(`/knowledge-bases/${activeKbId}/folders/tree`, { token })); } catch (err) {} }
  async function loadDocuments() {
    if (!activeKbId) return;
    try { const params = selectedFolderId ? `?folder_id=${selectedFolderId}` : ""; setDocuments(await api(`/knowledge-bases/${activeKbId}/documents${params}`, { token })); }
    catch (err) {}
  }
  async function uploadFile(e) {
    const file = e.target.files[0]; if (!file) return; setUploading(true);
    try { const fd = new FormData(); fd.append("file", file); if (selectedFolderId) fd.append("folder_id", selectedFolderId);
      const result = await api(`/knowledge-bases/${activeKbId}/upload`, { token, method: "POST", body: fd }); alert(result.message); e.target.value = ""; await loadDocuments(); }
    catch (err) { setError(err.message); } finally { setUploading(false); }
  }
  async function deleteDocument(docId) {
    if (!confirm("确定删除此文档？")) return;
    try { await api(`/knowledge-bases/${activeKbId}/documents/${docId}`, { token, method: "DELETE" }); await loadDocuments(); }
    catch (err) { setError(err.message); }
  }
  async function searchKB() {
    if (!searchQuery.trim()) return; setSearching(true);
    try { setSearchResults(await api("/knowledge-bases/search", { token, method: "POST", body: { query: searchQuery, kb_id: activeKbId, folder_id: selectedFolderId, top_k: 5 } })); }
    catch (err) { setError(err.message); } finally { setSearching(false); }
  }

  async function loadUsers() { try { setUsers(await api("/users", { token })); } catch (err) { setError(err.message); } }
  async function updateUser(userId, updates) {
    try { await api(`/users/${userId}`, { token, method: "PATCH", body: updates }); loadUsers(); }
    catch (err) { setError(err.message); }
  }
  async function deleteUser(userId) {
    if (!confirm("确定删除此用户？")) return;
    try { await api(`/users/${userId}`, { token, method: "DELETE" }); loadUsers(); }
    catch (err) { setError(err.message); }
  }
  async function loadSettings() { try { setSettings(await api("/settings", { token })); } catch (err) { setError(err.message); } }
  async function saveSetting() {
    if (!settingKey.trim()) return;
    try { await api(`/settings/${settingKey}`, { token, method: "PATCH", body: { value: settingValue } }); setSettingKey(""); setSettingValue(""); loadSettings(); }
    catch (err) { setError(err.message); }
  }
  async function deleteSetting(key) {
    try { await api(`/settings/${key}`, { token, method: "DELETE" }); loadSettings(); }
    catch (err) { setError(err.message); }
  }

  function logout() { localStorage.removeItem(TOKEN_KEY); setToken(""); setUser(null); setAgents([]); setThreads([]); setMessages([]); }
  async function handleAuth(event) {
    event.preventDefault(); setStatus("thinking"); setError("");
    try { const path = authMode === "login" ? "/auth/login" : "/auth/register";
      const payload = authMode === "login" ? { email: authForm.email, password: authForm.password } : authForm;
      const data = await api(path, { method: "POST", body: payload });
      localStorage.setItem(TOKEN_KEY, data.access_token); setToken(data.access_token); setUser(data.user);
    } catch (err) { setError(err.message); } finally { setStatus("ready"); }
  }
  async function sendMessage(event) {
    event.preventDefault(); if (!input.trim() || status === "thinking" || !activeAgent) return;
    const message = input.trim(); setInput(""); setStatus("thinking"); setError("");
    try {
      const res = await api("/chat", { token, method: "POST", body: { message, agent_id: activeAgent.id, thread_id: activeThreadId } });
      setMessages(prev => [...prev, { role: "user", content: message, created_at: new Date().toISOString() }, { ...res, role: "assistant", created_at: new Date().toISOString() }]);
      setActiveThreadId(res.thread_id);
      if (!activeThreadId) setThreads(prev => [{ id: res.thread_id, agent_id: activeAgent.id, title: message.slice(0, 60), created_at: new Date().toISOString(), updated_at: new Date().toISOString() }, ...prev]);
    } catch (err) { setError(err.message); } finally { setStatus("ready"); }
  }
  async function handleChoice(value, label) { setInput(value); await sendMessage({ preventDefault: () => {} }); }

  async function createAgent() {
    try { const agent = await api("/agents", { token, method: "POST", body: agentDraft }); setAgents(p => [...p, agent]); setActiveAgentId(agent.id);
      setAgentDraft({ name: "New Agent", description: "", system_prompt: "", model_name: "", temperature: 0 });
    } catch (err) { setError(err.message); }
  }
  async function deleteAgent(agentId) {
    try { await api(`/agents/${agentId}`, { token, method: "DELETE" }); setAgents(p => p.filter(a => a.id !== agentId)); if (activeAgentId === agentId) setActiveAgentId(null); }
    catch (err) { setError(err.message); }
  }
  async function createMcp() {
    try { const server = await api("/mcp-servers", { token, method: "POST", body: mcpDraft }); setMcpServers(p => [...p, server]);
      setMcpDraft({ name: "filesystem", transport: "stdio", command: "npx", args: "-y @modelcontextprotocol/server-filesystem D:/workspace", url: "" });
    } catch (err) { setError(err.message); }
  }
  async function deleteMcpServer(serverId) {
    try { await api(`/mcp-servers/${serverId}`, { token, method: "DELETE" }); setMcpServers(p => p.filter(s => s.id !== serverId)); }
    catch (err) { setError(err.message); }
  }
  async function createSkill() {
    try { const skill = await api("/skills", { token, method: "POST", body: skillDraft }); setSkills(p => [...p, skill]);
      setSkillDraft({ name: "code-review", title: "代码审查", description: "审查代码风险、可维护性和测试缺口", path: "skills/code-review" });
    } catch (err) { setError(err.message); }
  }
  async function deleteSkill(skillId) {
    try { await api(`/skills/${skillId}`, { token, method: "DELETE" }); setSkills(p => p.filter(s => s.id !== skillId)); }
    catch (err) { setError(err.message); }
  }
  function toggleFolder(id) { setExpandedFolders(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; }); }
  function selectFolder(id) { setSelectedFolderId(id === selectedFolderId ? null : id); }

  if (!token) {
    return (
      <div className="auth-shell">
        <div className="auth-panel">
          <div className="brand-mark" style={{ width: 56, height: 56, margin: "0 auto" }}><Sparkles size={28} /></div>
          <h2 style={{ textAlign: "center" }}>{authMode === "login" ? "登录" : "注册"}</h2>
          <form onSubmit={handleAuth}>
            {authMode === "register" && (
              <label>用户名<input value={authForm.username} onChange={(e) => setAuthForm({ ...authForm, username: e.target.value })} required /></label>
            )}
            <label>邮箱<input type="email" value={authForm.email} onChange={(e) => setAuthForm({ ...authForm, email: e.target.value })} required /></label>
            <label>密码<input type="password" value={authForm.password} onChange={(e) => setAuthForm({ ...authForm, password: e.target.value })} required minLength={6} /></label>
            {error && <div className="error-strip">{error}</div>}
            <button className="primary-button" type="submit" disabled={status === "thinking"}>{authMode === "login" ? "登录" : "注册"}</button>
          </form>
          <p style={{ textAlign: "center", fontSize: 13, color: "#9ea49b" }}>
            {authMode === "login" ? "还没有账号？" : "已有账号？"}
            <button className="text-button" onClick={() => setAuthMode(authMode === "login" ? "register" : "login")} style={{ marginLeft: 8 }}>{authMode === "login" ? "注册" : "登录"}</button>
          </p>
        </div>
      </div>
    );
  }

  return (
    <main className="shell">
      <aside className="left-panel">
        <div className="brand-lockup">
          <div className="brand-mark"><Sparkles size={24} /></div>
          <div className="core-copy"><p className="eyebrow">AI Agent Platform</p><strong>{user?.username}</strong></div>
          <div style={{ marginLeft: "auto" }}><button className="icon-button" onClick={logout} title="退出登录"><LogOut size={18} /></button></div>
        </div>
        <nav className="nav-list">
          {[
            { key: "chat", icon: <MessageSquare size={18} />, label: "对话" },
            { key: "agents", icon: <Bot size={18} />, label: "Agent 管理" },
            { key: "knowledge", icon: <Database size={18} />, label: "知识库" },
            { key: "users", icon: <Users size={18} />, label: "用户管理" },
            { key: "settings", icon: <Settings size={18} />, label: "系统设置" },
            { key: "mcp", icon: <Cable size={18} />, label: "MCP 配置" },
            { key: "skills", icon: <Wrench size={18} />, label: "Skill 管理" },
          ].map(({ key, icon, label }) => (
            <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)}>{icon}{label}</button>
          ))}
        </nav>

        {view === "chat" && activeAgent && (
          <>
            <div className="section-title"><h2>会话列表</h2><button className="icon-button" onClick={() => loadThreads(activeAgent.id)} title="刷新"><RefreshCcw size={14} /></button></div>
            <div className="nav-list">{threads.map(t => (
              <button key={t.id} className={activeThreadId === t.id ? "active" : ""} onClick={() => loadThreadMessages(t.id)}><MessageSquare size={16} />{t.title}</button>
            ))}</div>
          </>
        )}

        {view === "knowledge" && (
          <>
            <div className="section-title"><h2>知识库管理</h2></div>
            <div className="kb-create-form">
              <input placeholder="知识库名称" value={kbDraft.name} onChange={(e) => setKbDraft({ ...kbDraft, name: e.target.value })} />
              <input placeholder="描述（可选）" value={kbDraft.description} onChange={(e) => setKbDraft({ ...kbDraft, description: e.target.value })} />
              <button className="primary-button" onClick={createKnowledgeBase} style={{ width: "100%" }}><Plus size={16} /> 创建知识库</button>
            </div>
            <div className="kb-list">
              {knowledgeBases.map(kb => (
                <div key={kb.id} className={`kb-item ${activeKbId === kb.id ? "active" : ""}`} onClick={() => setActiveKbId(kb.id)}>
                  <Database size={16} />
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{kb.name}</span>
                  <button className="icon-button" onClick={(e) => { e.stopPropagation(); deleteKnowledgeBase(kb.id); }} title="删除"><Trash2 size={14} /></button>
                </div>
              ))}
              {knowledgeBases.length === 0 && <p className="muted">暂无知识库</p>}
            </div>
            {activeKbId && (() => {
              const actKb = knowledgeBases.find(k => k.id === activeKbId);
              return (
                <div className="kb-detail">
                  <div className="section-title"><h3>{actKb?.name || ""}</h3></div>
                  <div className="kb-section">
                    <div className="kb-section-header"><span>📁 文件夹</span><button className="text-button" onClick={() => createFolder()}><Plus size={14} /> 新建</button></div>
                    <div className="folder-tree">
                      {folderTree.map(node => (
                        <TreeNode key={node.id} node={node} expandedIds={expandedFolders} onToggle={toggleFolder} onSelect={selectFolder} selectedId={selectedFolderId} />
                      ))}
                      {folderTree.length === 0 && <p className="muted" style={{ fontSize: 12, padding: "4px 0" }}>暂无文件夹</p>}
                    </div>
                  </div>
                  <div className="kb-section">
                    <div className="kb-section-header"><span>📄 文档</span>
                      <label className="text-button" style={{ cursor: "pointer" }}><Upload size={14} />{uploading ? "上传中..." : "上传"}<input type="file" onChange={uploadFile} style={{ display: "none" }} disabled={uploading} /></label>
                    </div>
                    <div className="doc-list">
                      {documents.map(doc => (
                        <div key={doc.id} className="doc-item"><div><strong>{doc.original_filename}</strong>
                          <div style={{ fontSize: 11, color: "#9ea49b" }}>{doc.file_type} · {doc.file_size}B · {doc.status}</div>
                        </div><button className="icon-button" onClick={() => deleteDocument(doc.id)}><Trash2 size={14} /></button></div>
                      ))}
                      {documents.length === 0 && <p className="muted" style={{ fontSize: 12 }}>暂无文档</p>}
                    </div>
                  </div>
                  <div className="kb-section">
                    <div className="kb-section-header"><span>🔍 检索</span></div>
                    <div className="kb-search-bar">
                      <input placeholder="输入问题搜索知识库..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchKB()} />
                      <button className="primary-button" onClick={searchKB} disabled={searching}>{searching ? "搜索中..." : "搜索"}</button>
                    </div>
                    {searchResults.length > 0 && (
                      <div className="search-results">{searchResults.map((r, i) => (
                        <div key={i} className="search-result-item"><div className="result-meta">{r.document_name} · 相关度: {r.score.toFixed(2)}</div>
                          <div className="result-content">{r.content}</div></div>
                      ))}</div>
                    )}
                  </div>
                </div>
              );
            })()}
          </>
        )}

        {view === "users" && (
          <div className="config-view"><form className="config-form"><h3>用户管理</h3>
            <div className="item-list">
              {users.length === 0 && <p className="muted">暂无用户</p>}
              {users.map(u => (
                <div className="item-row" key={u.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div><strong>{u.username}</strong> ({u.email})
                    <span style={{ fontSize: 12, color: "#9ea49b", display: "block" }}>角色: {u.role} · {u.enabled ? "启用" : "禁用"}</span>
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button className="text-button" onClick={() => updateUser(u.id, { enabled: !u.enabled })} style={{ padding: "4px 8px", fontSize: 12 }}>{u.enabled ? "禁用" : "启用"}</button>
                    <button className="text-button" onClick={() => deleteUser(u.id)} style={{ padding: "4px 8px", fontSize: 12, color: "#f86180" }}>删除</button>
                  </div>
                </div>
              ))}
            </div>
          </form></div>
        )}

        {view === "settings" && (
          <div className="config-view"><form className="config-form"><h3>系统设置</h3>
            <div style={{ display: "grid", gap: 8, marginBottom: 16 }}>
              {settings.map(s => (
                <div key={s.id} className="item-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div><strong>{s.key}</strong><span style={{ fontSize: 12, color: "#9ea49b", display: "block" }}>{s.description}</span></div>
                  <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                    <input value={s.value} readOnly style={{ flex: 1, padding: "4px 8px", borderRadius: 4, border: "1px solid rgba(244,241,232,0.1)", background: "rgba(255,255,255,0.04)", color: "#f4f1e8", fontSize: 12 }} />
                    <button className="icon-button" onClick={() => deleteSetting(s.key)}><Trash2 size={14} /></button>
                  </div>
                </div>
              ))}
              {settings.length === 0 && <p className="muted">暂无设置</p>}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input placeholder="键名" value={settingKey} onChange={(e) => setSettingKey(e.target.value)} style={{ flex: 1, padding: "8px 12px", border: "1px solid rgba(244,241,232,0.1)", borderRadius: 6, background: "rgba(255,255,255,0.04)", color: "#f4f1e8" }} />
              <input placeholder="值" value={settingValue} onChange={(e) => setSettingValue(e.target.value)} style={{ flex: 2, padding: "8px 12px", border: "1px solid rgba(244,241,232,0.1)", borderRadius: 6, background: "rgba(255,255,255,0.04)", color: "#f4f1e8" }} />
              <button className="primary-button" onClick={saveSetting} style={{ padding: "8px 16px" }}><Plus size={16} /> 保存</button>
            </div>
          </form></div>
        )}

        {view === "agents" && (
          <ConfigView title="创建 Agent" onSubmit={createAgent}>
            <label>名称<input value={agentDraft.name} onChange={(event) => setAgentDraft({ ...agentDraft, name: event.target.value })} /></label>
            <label>描述<input value={agentDraft.description} onChange={(event) => setAgentDraft({ ...agentDraft, description: event.target.value })} /></label>
            <label>模型<input value={agentDraft.model_name} onChange={(event) => setAgentDraft({ ...agentDraft, model_name: event.target.value })} placeholder={activeAgent?.model_name} /></label>
            <label>系统提示语<textarea value={agentDraft.system_prompt} onChange={(event) => setAgentDraft({ ...agentDraft, system_prompt: event.target.value })} rows={5} /></label>
            <button className="primary-button" onClick={() => createAgent()}><Plus size={18} />创建 Agent</button>
            <ItemList items={agents} empty="还没有 Agent" onDelete={deleteAgent} />
          </ConfigView>
        )}
        {view === "mcp" && (
          <ConfigView title="配置 MCP Server" onSubmit={createMcp}>
            <label>名称<input value={mcpDraft.name} onChange={(event) => setMcpDraft({ ...mcpDraft, name: event.target.value })} /></label>
            <label>Transport<select value={mcpDraft.transport} onChange={(event) => setMcpDraft({ ...mcpDraft, transport: event.target.value })}><option value="stdio">stdio</option><option value="sse">sse</option><option value="http">http</option></select></label>
            <label>Command<input value={mcpDraft.command} onChange={(event) => setMcpDraft({ ...mcpDraft, command: event.target.value })} /></label>
            <label>Args<input value={mcpDraft.args} onChange={(event) => setMcpDraft({ ...mcpDraft, args: event.target.value })} /></label>
            <label>URL<input value={mcpDraft.url} onChange={(event) => setMcpDraft({ ...mcpDraft, url: event.target.value })} /></label>
            <button className="primary-button" onClick={() => createMcp()}><Plus size={18} />保存 MCP</button>
            <ItemList items={mcpServers} empty="还没有 MCP Server" onDelete={deleteMcpServer} />
          </ConfigView>
        )}
        {view === "skills" && (
          <ConfigView title="登记 Skill" onSubmit={createSkill}>
            <label>名称<input value={skillDraft.name} onChange={(event) => setSkillDraft({ ...skillDraft, name: event.target.value })} /></label>
            <label>标题<input value={skillDraft.title} onChange={(event) => setSkillDraft({ ...skillDraft, title: event.target.value })} /></label>
            <label>描述<input value={skillDraft.description} onChange={(event) => setSkillDraft({ ...skillDraft, description: event.target.value })} /></label>
            <label>路径<input value={skillDraft.path} onChange={(event) => setSkillDraft({ ...skillDraft, path: event.target.value })} /></label>
            <button className="primary-button" onClick={() => createSkill()}><Plus size={18} />保存 Skill</button>
            <ItemList items={skills} empty="还没有 Skill" onDelete={deleteSkill} />
          </ConfigView>
        )}
      </aside>

      {view === "chat" && (
        <section className="chat-panel">
          <header className="topbar"><h2>{activeAgent?.name || "Agent Chat"}</h2><div className="status-pill">{status === "thinking" ? "思考中..." : "就绪"}</div></header>
          <div className="message-list">
            {messages.map((message, i) => (<MessageRenderer key={i} message={message} onChoiceClick={handleChoice} />))}
            {status === "thinking" && (<article className="message assistant"><div className="avatar"><Sparkles size={17} /></div><div className="bubble typing"><span /><span /><span /></div></article>)}
          </div>
          {error && <div className="error-strip">{error}</div>}
          <form className="composer" onSubmit={sendMessage}>
            <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="给 Agent 发送消息.." rows={1} />
            <button type="submit" disabled={!input.trim() || status === "thinking"} aria-label="发送"><Send size={20} /></button>
          </form>
        </section>
      )}
      {view !== "chat" && view !== "knowledge" && (
        <section className="chat-panel">
          <header className="topbar"><h2>{viewTitle(view, activeAgent)}</h2></header>
          <div style={{ padding: 24, color: "#9ea49b" }}>选择左侧面板中的配置项进行管理。</div>
        </section>
      )}
      {view === "knowledge" && (
        <section className="chat-panel">
          <header className="topbar"><h2>知识库管理</h2></header>
          <div style={{ padding: 24, color: "#9ea49b" }}>请在左侧面板中操作知识库管理。</div>
        </section>
      )}
    </main>
  );
}

function viewTitle(view, activeAgent) {
  if (view === "agents") return "Agent 配置";
  if (view === "mcp") return "MCP 配置";
  if (view === "skills") return "Skill 管理";
  if (view === "knowledge") return "知识库管理";
  if (view === "users") return "用户管理";
  if (view === "settings") return "系统设置";
  return activeAgent?.name || "Agent Chat";
}

function ConfigView({ title, onSubmit, children }) {
  return (<div className="config-view"><form className="config-form" onSubmit={onSubmit}><h3>{title}</h3>{children}</form></div>);
}

function ItemList({ items, empty, onDelete }) {
  return (
    <div className="item-list">
      {items.length === 0 && <p className="muted">{empty}</p>}
      {items.map((item) => (
        <div className="item-row" key={item.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div><strong>{item.title || item.name}</strong>
            <span style={{ display: "block", fontSize: 12, color: "#9ea49b" }}>{item.description || item.transport || item.model_name || item.path}</span>
          </div>
          {onDelete && <button className="icon-button" onClick={() => onDelete(item.id)}><Trash2 size={14} /></button>}
        </div>
      ))}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
