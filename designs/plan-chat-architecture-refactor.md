# 聊天架构重构设计 — Model-Driven Agent Loop

> 基于 `learn-claude-code` 设计理念：**Agency comes from model, not from code orchestration**

## 一、核心设计理念

### 1.1 "Agency 来自模型"哲学

```
传统 Agent 范式（错误）:
┌─────────────────────────────────────────────────────────┐
│  User → [RAG 检索] → [Intent Router] → [Tool Selector] │
│         (硬编码)       (if-else 分支)    (规则引擎)      │
│                        ↓                                │
│                    LLM 生成                             │
└─────────────────────────────────────────────────────────┘
问题：智能来自代码编排，模型只是"执行者"

正确范式（Claude Code）:
┌─────────────────────────────────────────────────────────┐
│  User → messages[] → LLM（模型决定）→ 工具调用/返回     │
│         (模型主导)   (模型自主决策)   (模型决定停止)     │
└─────────────────────────────────────────────────────────┘
核心：模型是 driver，代码只是 harness（运行环境）
```

### 1.2 Harness 五要素

| 要素 | 职责 | 实现方式 |
|------|------|----------|
| **Tools** | MCP 工具池 + Skills | 首次加载后本地缓存，模型按需调用 |
| **Knowledge** | 产品文档/领域知识 | 通过 `retrieve_knowledge` 工具按需获取 |
| **Observation** | 消息历史/线程状态 | Context Manager 管理 |
| **Action** | 工具执行/响应生成 | Agent Loop 统一调度 |
| **Permissions** | 沙箱隔离/审批流程 | Hooks + 权限检查 |

### 1.3 核心原则

1. **模型决定何时调用工具** — 不是代码硬编码
2. **按需加载，非预加载** — Skill、Knowledge 都是需求驱动
3. **扩展点围绕循环，不改循环** — Hook 在外围，不改 Agent Loop
4. **上下文会耗尽，要主动管理** — 压缩、记忆、子任务隔离

## 二、当前架构问题分析

### 2.1 问题清单

| 问题 | 位置 | 影响 |
|------|------|------|
| **无条件 RAG 检索** | `ask_agent` 第 483-534 行 | 每轮必做 embedding + Chroma，耗时浪费 |
| **硬编码 Intent Router** | `ask_agent_stream_gen` 第 1055-1058 行 | if-else 分支决定路径，模型无自主权 |
| **工具每次重新加载** | `build_mcp_langchain_tools` 每轮调用 | MCP 连接/Schema 解析重复开销 |
| **知识库通过硬编码注入** | 第 638-642 行 RAG context 拼接 | 不是模型主动获取 |
| **复杂路径与非复杂路径分离** | T0/T1/T2 分流逻辑 | 割裂了统一的 Agent Loop |

### 2.2 问题代码定位

```python
# 问题 1: 无条件 RAG（第 483-534 行）
if bound_kb_ids:  # 只要 agent 绑定了 KB，就无条件检索
    for kb_id in bound_kb_ids:
        retriever = HybridRetriever(kb, db)
        hits = retriever.retrieve(...)  # embedding + Chroma 必做

# 问题 2: 硬编码 Intent Router（第 1055-1058 行）
if getattr(settings, "enable_intent_router", True):
    tier = _route_intent(message, settings, agent_has_kb)  # if-else 分支
    if tier == Tier.TOOLS:
        skip_kb = True  # 代码决定跳过 KB

# 问题 3: 工具每次重新加载（第 711-727 行）
if getattr(settings, "enable_mcp_tools", False):
    tools += build_mcp_langchain_tools(db, user_id)  # 每轮都调用
```

## 三、新架构设计

### 3.1 架构图

见上文 SVG 图。

### 3.2 核心组件

#### Agent Loop（核心循环）— 基于 s04_hooks

```python
def agent_loop(messages: list, tools: list, llm) -> Generator:
    """
    核心循环：模型决定一切，代码只执行模型请求
    
    设计原则（s04_hooks 核心）：
    - 循环本身永不改变
    - 权限检查移到 PreToolUse hook
    - 日志记录移到 PreToolUse/PostToolUse hooks
    - 上下文注入移到 UserPromptSubmit hook
    - 会话统计移到 Stop hook
    
    变化（vs s03）：
    - s03: if not check_permission(block): ...
    - s04: if trigger_hooks("PreToolUse", block): ...
    """
    while True:
        # 1. 调用模型（带工具定义）
        response = llm.invoke(messages, tools=tools)
        messages.append(response)
        
        # 2. 模型决定是否调用工具
        if response.stop_reason != "tool_use":
            # Stop hook：会话统计、结果改写
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            yield ("done", response.content)
            return
        
        # 3. 执行模型请求的工具
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            
            # ═════════════════════════════════════════════
            # s04 核心变化：Hook 替代硬编码权限检查
            # ═════════════════════════════════════════════
            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                # Hook 拦截，返回错误信息
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(blocked)
                })
                continue
            
            # 执行工具
            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
            
            # PostToolUse hook：日志、输出处理
            trigger_hooks("PostToolUse", block, output)
            
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output
            })
        
        # 4. 工具结果加入消息，循环继续
        messages.append({"role": "user", "content": results})
        yield ("status", f"已执行 {len(results)} 个工具")
```

#### Tool Pool（工具池）— 融合 Hook 系统

```python
class ToolPool:
    """
    工具池：首次加载后本地缓存，后续直接使用
    
    设计要点：
    - MCP 工具：首次建立连接 + 拉取 schema → 缓存到内存
    - Skills：首次扫描目录 → 缓存 manifest
    - 知识库：作为 retrieve_knowledge 工具（模型按需调用）
    - 失效机制：配置变更时通过 Hook 事件触发清除
    
    Hook 集成：
    - ToolInit Hook：工具初始化时触发（可注入元数据）
    - ToolPoolInvalidated 事件：配置变更时广播
    """
    _instance = None
    _cache: dict[str, ToolPoolEntry] = {}  # user_id -> ToolPoolEntry
    _lock = threading.Lock()
    
    @dataclass
    class ToolPoolEntry:
        """单个用户的工具池条目"""
        tools: list[Tool]
        mcp_connections: dict[str, MCPConnection]  # MCP server -> connection
        skill_manifests: dict[str, SkillManifest]  # skill_name -> manifest
        loaded_at: datetime
        
    @classmethod
    def get_tools(cls, user_id: int, db: Session) -> list[Tool]:
        cache_key = f"user:{user_id}"
        
        # 命中缓存 → 直接返回
        if cache_key in cls._cache:
            entry = cls._cache[cache_key]
            logger.info("ToolPool cache HIT for %s (loaded %s)", 
                       cache_key, entry.loaded_at)
            return entry.tools
        
        # 首次加载
        with cls._lock:
            entry = cls._load_tools_for_user(user_id, db)
            cls._cache[cache_key] = entry
            logger.info("ToolPool loaded %d tools for %s", len(entry.tools), cache_key)
            return entry.tools
    
    @classmethod
    def _load_tools_for_user(cls, user_id: int, db: Session) -> ToolPoolEntry:
        """
        为用户加载所有工具（首次）
        
        流程：
        1. 加载 MCP 工具（建立连接 + 拉取 schema）
        2. 加载 Skills（扫描目录 + 解析 manifest）
        3. 创建 retrieve_knowledge 工具
        4. 触发 ToolInit Hook（用户自定义初始化逻辑）
        """
        tools = []
        mcp_connections = {}
        skill_manifests = {}
        
        # ═════════════════════════════════════════════
        # 1. MCP 工具
        # ═════════════════════════════════════════════
        mcp_configs = db.scalars(
            select(MCPConfig).where(
                MCPConfig.user_id == user_id,
                MCPConfig.enabled == True
            )
        )
        
        for config in mcp_configs:
            try:
                # 建立连接
                conn = MCPConnection.connect(config.server_url, config.api_key)
                mcp_connections[config.name] = conn
                
                # 拉取工具 schema
                mcp_tools = conn.list_tools()
                for tool_schema in mcp_tools:
                    tool = StructuredTool(
                        name=f"mcp_{config.name}_{tool_schema['name']}",
                        description=tool_schema["description"],
                        args_schema=tool_schema["input_schema"],
                        func=lambda **kwargs, conn=conn, tool_name=tool_schema['name']: 
                            conn.call_tool(tool_name, kwargs)
                    )
                    tools.append(tool)
                
                logger.info(f"Loaded {len(mcp_tools)} MCP tools from {config.name}")
            except Exception as e:
                logger.error(f"Failed to load MCP {config.name}: {e}")
        
        # ═════════════════════════════════════════════
        # 2. Skills
        # ═════════════════════════════════════════════
        skill_dirs = Path("skills").glob("*/SKILL.md")
        for skill_dir in skill_dirs:
            try:
                manifest = SkillManifest.parse(skill_dir.parent)
                skill_manifests[manifest.name] = manifest
                
                # Skill 作为工具
                tool = StructuredTool(
                    name=f"skill_{manifest.name}",
                    description=manifest.description,
                    args_schema=manifest.args_schema,
                    func=lambda **kwargs, manifest=manifest: 
                        SkillExecutor.run(manifest, kwargs)
                )
                tools.append(tool)
                
                logger.info(f"Loaded skill: {manifest.name}")
            except Exception as e:
                logger.error(f"Failed to load skill {skill_dir.parent.name}: {e}")
        
        # ═════════════════════════════════════════════
        # 3. 知识库工具（替代无条件 RAG）
        # ═════════════════════════════════════════════
        kb_tool = cls._make_retrieve_knowledge_tool(user_id, db)
        tools.append(kb_tool)
        
        # ═════════════════════════════════════════════
        # 4. 触发 ToolInit Hook（用户自定义初始化）
        # ═════════════════════════════════════════════
        trigger_hooks("ToolInit", user_id, tools, db)
        
        return ToolPoolEntry(
            tools=tools,
            mcp_connections=mcp_connections,
            skill_manifests=skill_manifests,
            loaded_at=datetime.utcnow()
        )
    
    @classmethod
    def _make_retrieve_knowledge_tool(cls, user_id: int, db: Session) -> Tool:
        """
        知识库检索工具：模型按需调用，替代无条件 RAG
        
        设计要点：
        - 工具描述明确告诉模型何时使用
        - 调用时才做 embedding + Chroma 检索
        - 支持多知识库合并检索
        - 独立 DB session（线程安全）
        """
        def _run(query: str, k: int = 10) -> str:
            db2 = SessionLocal()
            try:
                # 检索用户绑定的知识库
                hits = HybridRetriever.search(user_id, query, db2, k=k)
                if not hits:
                    return "（知识库无相关内容）"
                
                # 格式化返回
                context = ContextBuilder.build(query, hits)
                return context
            except Exception as e:
                logger.error(f"retrieve_knowledge failed: {e}")
                return f"检索失败: {str(e)}"
            finally:
                db2.close()
        
        return StructuredTool(
            name="retrieve_knowledge",
            description=(
                "当回答需要以下信息时调用：\n"
                "1. 用户的历史偏好或过往讨论\n"
                "2. 产品文档、技术规范、API 文档\n"
                "3. 领域知识、业务规则\n"
                "输入：检索语句；输出：相关内容摘要"
            ),
            args_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索语句"},
                    "k": {"type": "integer", "description": "返回条数", "default": 10}
                },
                "required": ["query"]
            },
            func=_run,
        )
    
    @classmethod
    def invalidate(cls, user_id: int = None, reason: str = "config changed"):
        """
        配置变更时清除缓存
        
        触发场景：
        1. MCP 配置变更（新增/删除/修改）
        2. Skill 目录变更
        3. 知识库绑定变更
        """
        with cls._lock:
            if user_id:
                entry = cls._cache.pop(f"user:{user_id}", None)
                if entry:
                    # 关闭 MCP 连接
                    for conn in entry.mcp_connections.values():
                        conn.close()
                    logger.info(f"ToolPool invalidated for user {user_id}: {reason}")
            else:
                # 全局清除
                for entry in cls._cache.values():
                    for conn in entry.mcp_connections.values():
                        conn.close()
                cls._cache.clear()
                logger.info(f"ToolPool invalidated globally: {reason}")
        
        # 触发 ToolPoolInvalidated 事件
        trigger_hooks("ToolPoolInvalidated", user_id, reason)


# ═══════════════════════════════════════════════════════════
#  TOOL_HANDLERS Dispatch Map（s04_hooks 核心）
# ═══════════════════════════════════════════════════════════

TOOL_HANDLERS = {
    # 内置工具
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
    
    # 知识库工具
    "retrieve_knowledge": ToolPool._retrieve_knowledge_handler,
    
    # MCP 工具（动态注册）
    # 格式: "mcp_{server_name}_{tool_name}": mcp_handler
    
    # Skills（动态注册）
    # 格式: "skill_{skill_name}": skill_handler
}


def register_tool_handler(name: str, handler: callable):
    """动态注册工具处理器"""
    TOOL_HANDLERS[name] = handler
    logger.info(f"Registered tool handler: {name}")
```

#### Hooks（扩展点）— 基于 s04_hooks 设计

```python
# ═══════════════════════════════════════════════════════════
#  Hook 注册表（s04_hooks 核心）
# ═══════════════════════════════════════════════════════════

HOOKS = {
    "UserPromptSubmit": [],  # 用户提交消息时（可注入上下文）
    "PreToolUse": [],        # 工具执行前（可拦截/修改参数）
    "PostToolUse": [],       # 工具执行后（可修改结果）
    "Stop": [],              # 响应生成后（可改写最终答案）
}

def register_hook(event: str, callback):
    """注册 Hook 回调函数"""
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args) -> str | None:
    """
    触发 Hook 链
    
    返回值：
    - None：继续执行（不拦截）
    - str：拦截原因（直接返回给模型作为 tool_result）
    """
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:  # 拦截信号
            return result
    return None


# ═══════════════════════════════════════════════════════════
#  内置 Hooks（权限控制、日志、输出处理）
# ═══════════════════════════════════════════════════════════

def permission_hook(block) -> str | None:
    """
    PreToolUse: 权限检查（s03 check_permission 移植）
    
    拦截场景：
    1. 危险命令（rm -rf /, sudo, shutdown）
    2. 破坏性操作（rm, chmod 777）→ 需用户确认
    3. 写入工作区外文件 → 需用户确认
    """
    if block.name == "bash":
        # 黑名单（无条件拦截）
        DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
        for pattern in DENY_LIST:
            if pattern in block.input.get("command", ""):
                logger.warning(f"⛔ Blocked dangerous command: {pattern}")
                return f"Permission denied: '{pattern}' is not allowed"
        
        # 灰名单（需确认）
        DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]
        for kw in DESTRUCTIVE:
            if kw in block.input.get("command", ""):
                logger.warning(f"⚠ Potentially destructive: {block.input}")
                # 实际实现中需要前端确认机制
                return f"Permission denied: destructive operation requires confirmation"
    
    if block.name in ("write_file", "edit_file"):
        # 写入工作区外检查
        path = block.input.get("path", "")
        if not is_safe_path(path):
            logger.warning(f"⚠ Writing outside workspace: {path}")
            return f"Permission denied: cannot write outside workspace"
    
    return None  # 不拦截

def log_hook(block):
    """PreToolUse: 记录所有工具调用"""
    args_preview = str(list(block.input.values())[:2])[:60]
    logger.info(f"[HOOK] {block.name}({args_preview})")
    return None

def large_output_hook(block, output: str):
    """PostToolUse: 大输出警告"""
    if len(output) > 100000:
        logger.warning(f"[HOOK] ⚠ Large output from {block.name}: {len(output)} chars")
    return None

def context_inject_hook(query: str, user_id: int, db: Session):
    """UserPromptSubmit: 注入上下文（当前工作目录、用户信息）"""
    logger.info(f"[HOOK] UserPromptSubmit: user={user_id}")
    # 可注入系统提示词、当前时间等
    return None

def summary_hook(messages: list):
    """Stop: 会话统计"""
    tool_count = sum(1 for m in messages 
                     for b in (m.content if isinstance(m.content, list) else [])
                     if isinstance(b, dict) and b.get("type") == "tool_result")
    logger.info(f"[HOOK] Stop: session used {tool_count} tool calls")
    return None

# 注册内置 Hooks
register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)


# ═══════════════════════════════════════════════════════════
#  用户自定义 Hooks（从 DB 加载）
# ═══════════════════════════════════════════════════════════

def load_user_hooks(user_id: int, db: Session):
    """
    从 DB 加载用户自定义 Hooks
    
    Hook 模型结构：
    - user_id: 用户 ID
    - hook_type: "UserPromptSubmit" / "PreToolUse" / "PostToolUse" / "Stop"
    - matcher: 正则匹配（可选）
    - action: "block" / "modify" / "log"
    - script: Python 代码（沙箱执行）
    """
    hooks = db.scalars(
        select(Hook).where(
            Hook.user_id == user_id,
            Hook.enabled == True,
        )
    )
    
    for hook in hooks:
        # 创建回调函数
        def callback(*args, hook=hook):
            return execute_user_hook(hook, *args)
        
        # 注册到对应事件
        register_hook(hook.hook_type, callback)
    
    logger.info(f"Loaded {len(list(hooks))} user hooks for user {user_id}")


def execute_user_hook(hook: Hook, *args) -> str | None:
    """
    执行用户自定义 Hook（沙箱环境）
    
    安全措施：
    1. 限制执行时间（5s 超时）
    2. 禁止危险操作（文件读写、网络访问）
    3. 返回值仅限字符串或 None
    """
    try:
        # 创建受限执行环境
        safe_globals = {
            "__builtins__": {
                "str": str, "int": int, "float": float,
                "bool": bool, "list": list, "dict": dict,
                "len": len, "print": lambda *a: None,  # 禁用 print
            }
        }
        
        # 执行用户脚本
        exec_result = {}
        exec(hook.script, safe_globals, exec_result)
        
        if "hook_handler" in exec_result:
            return exec_result["hook_handler"](*args)
        
        return None
    except Exception as e:
        logger.error(f"User hook {hook.id} failed: {e}")
        return None
```

### 3.3 数据流

```
用户发送消息
    ↓
messages.append(HumanMessage(content=message))
    ↓
agent_loop(messages, tools=ToolPool.get_tools(user_id), llm)
    ↓
LLM 调用（带工具定义）
    ↓
模型决定：
├── 直接回答 → yield ("done", text)
├── 调用 retrieve_knowledge → 执行 → 结果加入 messages → 循环
├── 调用 MCP 工具 → 执行 → 结果加入 messages → 循环
└── 调用 Skill → 执行 → 结果加入 messages → 循环
    ↓
Context Manager:
├── Token 统计
├── 超限自动压缩
└── Memory 持久化（可选）
```

## 四、与旧架构对比

| 维度 | 旧架构（硬编码编排） | 新架构（Model-Driven） |
|------|---------------------|----------------------|
| **RAG 检索** | 每轮无条件做 embedding + Chroma | 模型按需调用 `retrieve_knowledge` 工具 |
| **Intent Router** | if-else 三档分流（T0/T1/T2） | 删除，模型自主决定路径 |
| **工具加载** | 每轮重新 `build_mcp_langchain_tools` | Tool Pool 缓存，首次加载后复用 |
| **知识注入** | 硬编码拼接 RAG context | 模型调用工具获取 |
| **扩展方式** | 改代码加分支 | 加一行 handler 或一个 hook |
| **循环结构** | 多个路径分离 | 统一 agent_loop，不改代码 |

## 五、实施步骤（基于 s04_hooks）

### Phase 1: 实现 Hook 系统

1. **创建** `app/hooks.py`
   - HOOKS 注册表
   - `register_hook()` / `trigger_hooks()` 函数
   - 内置 Hooks（permission_hook, log_hook, large_output_hook）
   
2. **创建 Hook 模型**（DB）
   ```python
   class Hook(Base):
       __tablename__ = "hooks"
       id = Column(Integer, primary_key=True)
       user_id = Column(Integer, ForeignKey("users.id"))
       hook_type = Column(String(50))  # UserPromptSubmit/PreToolUse/PostToolUse/Stop
       matcher = Column(Text)  # 正则匹配
       action = Column(String(20))  # block/modify/log
       script = Column(Text)  # Python 代码
       enabled = Column(Boolean, default=True)
   ```

3. **添加** DB 迁移脚本
   ```bash
   alembic revision --autogenerate -m "add_hooks_table"
   alembic upgrade head
   ```

### Phase 2: 重构 agent_loop（核心）

1. **提取** `app/agent_loop.py`
   - 统一的 `agent_loop` 函数
   - 融入 Hook 调用点
   - 删除所有 if-else 分支判断

2. **删除** 旧架构代码
   - `ask_agent` 无条件 RAG（第 483-534 行）
   - `ask_agent_stream_gen` Intent Router（第 1055-1082 行）
   - T0/T1/T2 分流逻辑

3. **保留** 核心功能
   - Token 统计 + 上下文压缩
   - 超时控制 + 心跳
   - 错误处理

### Phase 3: 实现 Tool Pool 缓存

1. **创建** `app/tool_pool.py`
   - `ToolPool` 单例类
   - 缓存 MCP 连接 + Skills manifest
   - `invalidate()` 失效机制

2. **实现** 工具加载逻辑
   - MCP：建立连接 → list_tools() → 缓存 schema
   - Skills：扫描目录 → 解析 SKILL.md → 缓存 manifest
   - retrieve_knowledge：创建工具定义

3. **集成** 配置变更事件
   - MCP CRUD 操作触发 `ToolPool.invalidate()`
   - Skill 目录变更监听（可选）

### Phase 4: 集成到 API

1. **修改** `app/api.py` `/chat-stream` 端点
   ```python
   @app.post("/chat-stream")
   async def chat_stream(request: ChatRequest, user = Depends(get_current_user)):
       # 1. UserPromptSubmit Hook
       trigger_hooks("UserPromptSubmit", request.message, user.id, db)
       
       # 2. 获取工具池（缓存）
       tools = ToolPool.get_tools(user.id, db)
       
       # 3. Agent Loop
       messages = [{"role": "user", "content": request.message}]
       for event_type, event_data in agent_loop(messages, tools, llm):
           yield f"data: {json.dumps({event_type: event_data})}\n\n"
   ```

2. **添加** Hook 管理 API
   ```python
   @app.get("/api/hooks")
   async def list_hooks(user = Depends(get_current_user)):
       ...
   
   @app.post("/api/hooks")
   async def create_hook(hook: HookCreate, user = Depends(get_current_user)):
       ...
   ```

### Phase 5: 测试与验证

1. **单元测试** `tests/test_agent_loop.py`
   - Hook 拦截逻辑
   - Tool Pool 缓存命中/未命中
   - retrieve_knowledge 按需调用

2. **集成测试** `tests/test_chat_e2e.py`
   - 简单聊天（不触发知识库）
   - 知识库聊天（模型调用 retrieve_knowledge）
   - 工具调用（PreToolUse Hook 拦截）

3. **性能对比**
   - 旧架构延迟 vs 新架构延迟
   - Tool Pool 缓存命中率
   - Token 使用量对比

## 六、关键代码变更

### 6.1 删除的代码

```python
# 删除：无条件 RAG 检索（ask_agent 第 483-534 行）
if bound_kb_ids:
    for kb_id in bound_kb_ids:
        retriever = HybridRetriever(kb, db)
        hits = retriever.retrieve(...)  # 每轮必做

# 删除：硬编码 Intent Router（ask_agent_stream_gen 第 1055-1082 行）
if getattr(settings, "enable_intent_router", True):
    tier = _route_intent(message, settings, agent_has_kb)
    if tier == Tier.DIRECT:
        # 简单路径
    elif tier == Tier.TOOLS:
        # 工具路径
    else:
        # 全量路径
```

### 6.2 新增的代码

```python
# 新增：ToolPool 单例缓存
class ToolPool:
    _cache: dict[str, list[Tool]] = {}
    
    @classmethod
    def get_tools(cls, user_id: int, db: Session) -> list[Tool]:
        # 首次加载后缓存
        pass

# 新增：统一 agent_loop
def agent_loop(messages, tools, llm) -> Generator:
    while True:
        response = llm.invoke(messages, tools=tools)
        if response.stop_reason != "tool_use":
            return response.content
        # 执行工具，循环继续
```

## 七、预期收益

| 指标 | 当前 | 预期 | 改进 |
|------|------|------|------|
| **简单聊天延迟** | 3-5s（T0 路径）| 1-2s | -50% |
| **知识库聊天延迟** | 8-15s（必检索）| 5-8s（按需检索）| -40% |
| **工具调用延迟** | 每次 500ms（重加载）| 首次 500ms，后续 0ms | -90% |
| **代码复杂度** | 1200+ 行 if-else | 300 行核心循环 | -75% |
| **可扩展性** | 改代码加分支 | 加一行 handler | +10x |

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| **模型不调用知识库工具** | 答案可能缺少上下文 | 工具描述明确指导；fallback 提示 |
| **工具缓存失效不及时** | 配置变更不生效 | 监听配置变更事件；主动 invalidate |
| **循环次数过多** | Token 耗尽 | max_iterations 限制；压缩机制 |
| **并发安全问题** | 缓存竞争 | 线程锁保护 |

## 九、参考

- `learn-claude-code` 设计理念：https://github.com/shareAI-lab/learn-claude-code
- Claude Code 源码分析：s01-s20 章节渐进式学习路径
- 当前实现：`app/agent.py` 1300+ 行
