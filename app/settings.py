from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    langsmith_project: str = Field(default="local-langchain-agent", alias="LANGSMITH_PROJECT")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    database_url: str = Field(default=f"sqlite:///{ROOT_DIR / 'agent.db'}", alias="DATABASE_URL")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60 * 24 * 7, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # ── Vector Store Configuration ──────────────────────────────────
    # Supported backends: "chroma", "faiss", "milvus"
    vector_store_backend: str = Field(default="chroma", alias="VECTOR_STORE_BACKEND")
    vector_store_path: str = Field(default=str(ROOT_DIR / "vector_db"), alias="VECTOR_STORE_PATH")
    # Milvus-specific (only used when backend="milvus")
    milvus_host: str = Field(default="localhost", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, alias="MILVUS_PORT")
    milvus_collection_prefix: str = Field(default="kb_", alias="MILVUS_COLLECTION_PREFIX")

    # ── Context & Memory Subsystem (ADR-021 / 022 / 023) ──
    # 全部默认关闭：开启前不影响任何现有行为（后向兼容）。
    # 统一上下文管理：用预算装配 [system+pinned] + [记忆召回] + [会话摘要] + [最近K轮] + [当前轮]。
    enable_context_service: bool = Field(default=False, alias="ENABLE_CONTEXT_SERVICE")
    # gbrain 式 Retrieval Reflex：零 LLM 确定性指针层，每轮扫描当前消息实体→注入精简指针。
    enable_retrieval_reflex: bool = Field(default=False, alias="ENABLE_RETRIEVAL_REFLEX")
    # 语义回忆（Chroma 每用户集合）。默认关；需 embedding 可用。
    enable_memory_recall: bool = Field(default=False, alias="ENABLE_MEMORY_RECALL")
    # 会话内保留原样的轮数（K）。
    context_service_recent_turns: int = Field(default=10, alias="CONTEXT_SERVICE_RECENT_TURNS")
    # 为模型回复预留的窗口比例（不计入对话预算）。
    context_service_reserved_reply_ratio: float = Field(default=0.25, alias="CONTEXT_SERVICE_RESERVED_REPLY_RATIO")
    # 未知模型时的兜底上下文窗口（token）。已知模型走内置映射表。
    context_service_model_window: int = Field(default=128000, alias="CONTEXT_SERVICE_MODEL_WINDOW")
    # Retrieval Reflex 单轮最多注入的指针条数（cap，防上下文膨胀）。
    context_service_reflex_cap: int = Field(default=6, alias="CONTEXT_SERVICE_REFLEX_CAP")
    # Chroma 语义回忆每轮最多返回条数。
    context_service_recall_k: int = Field(default=4, alias="CONTEXT_SERVICE_RECALL_K")

    # ── 写入/治理开关（默认关，防记忆污染）──
    # P5 隐式提取：对话末用 LLM 提取候选进 pending 队列（需用户确认）。
    enable_implicit_extraction: bool = Field(default=False, alias="ENABLE_IMPLICIT_EXTRACTION")
    # P6 后台富集 cron：去重/矛盾检测/衰减/会话摘要 Promotion。
    enable_memory_enricher: bool = Field(default=False, alias="ENABLE_MEMORY_ENRICHER")
    memory_enricher_interval_seconds: int = Field(default=3600, alias="MEMORY_ENRICHER_INTERVAL_SECONDS")
    # P7 增强：召回不足时注入诚实提示；Reflex 指针 + Chroma 结果 RRF 融合。
    enable_gap_analysis: bool = Field(default=False, alias="ENABLE_GAP_ANALYSIS")
    enable_rrf: bool = Field(default=False, alias="ENABLE_RRF")
    # ── Workspace Memory Bridge (ADR-024) ──
    # 将项目级长期记忆（.workbuddy/memory/MEMORY.md，由 AI 编码会话策展）注入聊天上下文，
    # 解决「跨会话聊天无项目上下文」问题。默认关，开启前不影响现有行为。
    enable_workspace_memory: bool = Field(default=False, alias="ENABLE_WORKSPACE_MEMORY")
    # 注入内容的最大 token 预算（中文-aware 估算），超出截断保头尾部。
    workspace_memory_max_tokens: int = Field(default=6000, alias="WORKSPACE_MEMORY_MAX_TOKENS")
    # MEMORY.md 相对 ROOT_DIR 的路径（可被子项目覆盖）。
    workspace_memory_path: str = Field(
        default=str(ROOT_DIR / ".workbuddy" / "memory" / "MEMORY.md"),
        alias="WORKSPACE_MEMORY_PATH",
    )
    # ── 用户长期记忆跨会话召回 (ADR-025, Tier1) ──
    # 会话开始即无条件加载该用户 active 且 layer>=1 的偏好/事实/纠正，
    # 作为 system 块注入，保证跨会话召回（与当前轮消息内容无关）。
    # 默认关；开启前不影响现有行为。
    enable_user_profile_memory: bool = Field(default=False, alias="ENABLE_USER_PROFILE_MEMORY")
    # 画像块 token 硬上限（中文-aware 估算）；超限按 importance 截断。
    user_profile_max_tokens: int = Field(default=2000, alias="USER_PROFILE_MAX_TOKENS")
    # 单次最多加载的画像条数（防极端情况下全表扫描）。
    user_profile_count_cap: int = Field(default=30, alias="USER_PROFILE_COUNT_CAP")

    # ── MCP / Skill / Hook 扩展 (ADR: MCP-Skill-Hook) ──
    # 全部默认关闭：开启前不影响任何现有行为（后向兼容，铁律）。
    enable_mcp_tools: bool = Field(default=False, alias="ENABLE_MCP_TOOLS")
    mcp_max_iterations: int = Field(default=5, alias="MCP_MAX_ITERATIONS")
    enable_skill_tools: bool = Field(default=False, alias="ENABLE_SKILL_TOOLS")
    enable_hooks: bool = Field(default=False, alias="ENABLE_HOOKS")
    # 安全闸门：MCP/Skill/Hook 启用前强制安全扫描；默认开。
    enable_security_gate: bool = Field(default=True, alias="ENABLE_SECURITY_GATE")
    mcp_default_timeout_ms: int = Field(default=30000, alias="MCP_DEFAULT_TIMEOUT_MS")
    # 单条 MCP 工具调用的最长耗时上限（毫秒）。用于在服务端 timeout_ms 设得过高时
    # 收敛最坏延迟（避免一次搜索卡 70-120s）。正常搜索 < 该上限，不损功能。
    mcp_tool_max_timeout_ms: int = Field(default=60000, alias="MCP_TOOL_MAX_TIMEOUT_MS")
    # 工具结果缓存 TTL（秒）。相同 (user, server, tool, args) 命中后直接返回，零延迟；
    # 不缓存变更类工具（create/send/delete/...）与失败结果。避免重复实时查询耗时。
    mcp_tool_cache_ttl_sec: int = Field(default=300, alias="MCP_TOOL_CACHE_TTL_SEC")
    # 单 MCP server 最大并发调用（信号量限流，防万级会话下连接/资源耗尽）。
    mcp_max_concurrency: int = Field(default=8, alias="MCP_MAX_CONCURRENCY")
    # 熔断：连续失败达阈值→熔断 cooldown；cooldown 后首次调用为探测（半开）。
    mcp_circuit_max_failures: int = Field(default=5, alias="MCP_CIRCUIT_MAX_FAILURES")
    mcp_circuit_cooldown_secs: float = Field(default=60.0, alias="MCP_CIRCUIT_COOLDOWN_SECS")

    # ── 聊天每轮性能优化 (plan-chat-perf-v2) ──
    # 每根优化独立开关：关闭即回退到当前 complex_path 行为（零能力回归、可灰度、可一键回退）。
    # §1.1 工具池缓存：避免每轮重建 StructuredTool（事件失效，非时间过期）。
    enable_tool_pool: bool = Field(default=True, alias="ENABLE_TOOL_POOL")
    # §1.2 Catalog 瘦身：见 mcp_tools.get_mcp_tool_catalog（随 enable_tool_pool 一并生效）。
    # §1.3 KB 前置门控：无实体/召回意图的平凡轮跳过 semantic_recall / retrieval_reflex。
    enable_kb_gate: bool = Field(default=True, alias="ENABLE_KB_GATE")
    # §2.1 Fast Intent Router：闲聊/短句直答（T0）、实时数据仅工具（T1）、其余全量（T2）。
    enable_intent_router: bool = Field(default=True, alias="ENABLE_INTENT_ROUTER")
    # §2.2 按需 KB 工具 retrieve_knowledge：关闭自动语义回忆，改由模型按需调用（最大收益项，默认关）。
    enable_ondemand_kb: bool = Field(default=False, alias="ENABLE_ONDEMAND_KB")
    # §2.3 top-k 工具相关性剪枝：bind_tools 前仅绑定最相关 top-k（仅影响绑定列表，不改缓存）。
    enable_tool_prune: bool = Field(default=True, alias="ENABLE_TOOL_PRUNE")
    tool_prune_top_k: int = Field(default=8, alias="TOOL_PRUNE_TOP_K")
    
    # ── Model-Driven Agent Loop V2 (learn-claude-code) ──
    # 基于 learn-claude-code 的重构架构：模型决定何时调用工具，代码只执行模型请求。
    # 开启后：
    # - 删除无条件 RAG（改为 retrieve_knowledge 工具）
    # - 删除 Intent Router（模型自主决定路径）
    # - Tool Pool 缓存（MCP/Skills 首次加载后缓存）
    # - Hook 系统管理所有扩展点
    use_agent_v2: bool = Field(default=False, alias="USE_AGENT_V2")
    # V2 知识库工具开关（仅在 use_agent_v2=True 时生效）
    enable_knowledge_tool: bool = Field(default=True, alias="ENABLE_KNOWLEDGE_TOOL")
    
    # 部署模式：saas（多租户）| private（私有化单租户）。影响配额/隔离策略。
    deploy_mode: str = Field(default="saas", alias="DEPLOY_MODE")

    # ── Hook 沙箱隔离（v1 进程级 + 资源限制；Phase 4 升容器/gVisor）──
    # 沙箱模式：process=进程级隔离(资源限制+网络隔离)；disabled=信任模式(不限制，仅超时)；
    #           container=容器/gVisor 隔离(暂未实现，回退 process 并告警)。
    hook_sandbox_mode: str = Field(default="process", alias="HOOK_SANDBOX_MODE")
    hook_sandbox_network_block: bool = Field(default=True, alias="HOOK_SANDBOX_NETWORK_BLOCK")
    hook_sandbox_cpu_secs: int = Field(default=10, alias="HOOK_SANDBOX_CPU_SECS")
    hook_sandbox_mem_bytes: int = Field(default=268435456, alias="HOOK_SANDBOX_MEM_BYTES")  # 256MB
    hook_sandbox_fsize_bytes: int = Field(default=10485760, alias="HOOK_SANDBOX_FSIZE_BYTES")  # 10MB
    hook_sandbox_cwd: str = Field(default="/tmp/hook_sandbox", alias="HOOK_SANDBOX_CWD")
    # 输入/输出体积上限，防 stdin/stdout 内存炸弹（万级并发下尤其关键）。
    hook_sandbox_max_input_bytes: int = Field(default=65536, alias="HOOK_SANDBOX_MAX_INPUT_BYTES")   # 64KB
    hook_sandbox_max_output_bytes: int = Field(default=1048576, alias="HOOK_SANDBOX_MAX_OUTPUT_BYTES")  # 1MB
    # 沙箱试跑：启用 Hook 前在真实沙箱内跑一次探针，确认能产出合法决策 JSON。
    enable_sandbox_dry_run: bool = Field(default=True, alias="ENABLE_SANDBOX_DRY_RUN")
    hook_sandbox_probe_timeout_ms: int = Field(default=5000, alias="HOOK_SANDBOX_PROBE_TIMEOUT_MS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
