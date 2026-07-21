# 联网查询（Web Search）集成设计方案

> 目标：在不破坏现有架构、不引入额外运维负担的前提下，给自托管 AI 工作台加上**免费/免 API key 优先**的联网查询能力，并复用已有的 Fast Intent Router / Tool Pool / KB 门控。

## 1. 问题定位（为什么现在「用不上」）

你引用的 CSDN 方案 `pskill9/web-search` 是一个 **stdio 型 MCP Server**：
- 以 `node build/index.js` 起一个本地子进程，靠 stdin/stdout 走 JSON-RPC；
- 内部抓取 Google 搜索结果页，解析出 `title / url / description` 返回；
- 免 key、免费，但依赖同 IP 不被 Google 限流、且页面结构不频繁变动。

而本项目 `app/mcp_client.py` 第 8 行明确写道：

> `stdio 传输本批不启用（用户决策：先远端）。后续可在此扩展子进程管理。`

即**当前 MCP 客户端只支持 Streamable-HTTP / SSE（远端）传输**，没有 stdio 子进程管理。因此：
- 博客那个 server 是 stdio，**现有框架连不上** → 这就是「用不上」的根因，不是配置问题。
- 即便强行接，API 跑在 Docker 容器里，容器内没有 `node` 也没有构建好的 `web-search` 包，也起不了子进程。

## 2. 设计约束（来自项目既有铁律）

- 自托管 Docker 部署，API 容器（`ai-agent-api`）只挂 Python 运行时；**尽量不引入 node 依赖**。
- `startup` 不联网、不阻塞；出网走 `app/http_client` 的代理兜底（`request_with_fallback`）。
- 复用现有能力：Fast Intent Router（T1 实时→仅工具）、Tool Pool 缓存、top-k 剪枝、KB 门控。
- 每项能力带**独立开关**，关 → 零能力回归、可灰度、可一键回退。
- 安全：出网域名白名单防 SSRF；结果截断防 token 爆炸；失败优雅降级不崩。

## 3. 三个可选路径

### 方案 A —— 内置联网搜索工具（推荐为默认）
新增 `app/web_search.py`：一个**provider 抽象 + 原生 LangChain 工具**，纯 Python（复用已有 `httpx`），无需 node。

- `WebSearchProvider` 抽象：`search(query, limit) -> list[{title, url, snippet}]`。
- 默认实现 `GoogleScrapeProvider`（镜像博客思路，但用 `app/http_client.request_with_fallback` 出网，代理不可达自动直连）。
- 兜底 `DuckDuckGoProvider`（`html.duckduckgo.com/html/`）。
- 可选 `TavilyProvider`（填 `WEB_SEARCH_API_KEY` 即用，质量/稳定性更好，免费额度 1000 次/月）。
- `build_web_search_tool()` → `StructuredTool`，`ENABLE_WEB_SEARCH` 开启时加入 `ask_agent` 工具集（与 MCP/skill/use_skill 并列）。
- **自动路由**：`_REALTIME_RE` 已含 `搜索|查询|查一下|帮我查|帮我搜` → T1（仅工具、跳过 KB）→ 联网工具被绑定；其余走 T2 时该工具同样可用（用户可主动「上网查一下」）。
- **缓存**：只读结果走 `mcp_client._tool_cache`（或 web_search 自带短时缓存），收敛重复查询。
- **Docker**：零新增依赖，容器只需能出网（已有代理兜底）。对比方案 B 的 node 依赖，这是最大优势。

### 方案 B —— 给 MCP 客户端补 stdio 传输
让现有 MCP 框架能直接挂 `pskill9/web-search`（以及任意 stdio MCP server）。

- 新增 `StdioMCPClient`：用 `subprocess` 拉起 `command + args`，通过 stdin/stdout 做 JSON-RPC（initialize/list_tools/call_tool）。
- `MCPConnectionManager` 按 `(user_id, server_id)` 池化子进程，带生命周期/健康检查/崩溃重建；多租户需进程级隔离 + 资源上限（防某用户拖垮整容器）。
- **Docker 改造**：`Dockerfile`/compose 需装 `node` + 构建 `web-search` 并 bake 进镜像（或挂 volume）。
- 安全：spawn node 需沙箱/受限权限；出网域名仍需白名单。
- 优点：通用，未来任何 stdio MCP 都能用；完全复用 Tool Pool / 剪枝 / catalog。
- 缺点：运维重、容器要带 node、子进程管理复杂、Google 仍可能限流容器 IP。

### 方案 C —— A + B 都做（★推荐）
- **A 作为默认开启路径**：立刻可用、零新增依赖、部署简单，直接解决「没有联网功能」。
- **B 作为进阶路径**：给需要「原版 pskill9 server / 其他 stdio MCP」的用户提供扩展能力，但默认不启用、文档标注 Docker 前置条件。
- 两者都受 `ENABLE_WEB_SEARCH` / `ENABLE_MCP_TOOLS` 门控，且都汇入同一套 Intent Router + Tool Pool。

## 4. 详细设计（以方案 A 为主）

### 4.1 数据 / 接口契约
```python
@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str

class WebSearchProvider(Protocol):
    name: str
    def search(self, query: str, limit: int = 5) -> list[SearchHit]: ...
```

### 4.2 工具封装（复用 perf-v2 的 _call_mcp_tool 同款自包含模式）
```python
def build_web_search_tool() -> StructuredTool:
    def _run(query: str, limit: int = 5) -> str:
        from app.web_search import get_provider
        try:
            hits = get_provider().search(query, limit=max(1, min(limit, 10)))
        except Exception as e:
            logger.warning("web_search failed: %s", e)
            return "[web search unavailable] 暂时无法联网检索，请稍后重试。"
        if not hits:
            return "未找到相关网页结果。"
        return "\n\n".join(f"{i+1}. {h.title}\n{h.url}\n{h.snippet}"
                           for i, h in enumerate(hits))
    return StructuredTool.from_function(
        name="web_search",
        description=("联网搜索实时网页结果（Google/DuckDuckGo）。当用户需要最新资讯、"
                     "实时数据、新闻、或明确说“搜索/查一下/上网查”时调用。"),
        func=_run,
        args_schema=...,
    )
```

### 4.3 路由接入（无需改路由逻辑，仅需保证工具被绑定）
- `ask_agent` 工具装配段已有 `if getattr(settings, "enable_mcp_tools", False)` 等分支；在同区块加：
  ```python
  if getattr(settings, "enable_web_search", False):
      try:
          tools.append(build_web_search_tool())
      except Exception as e:
          logger.warning("web_search 工具加载失败（优雅降级）: %s", e)
  ```
- T1（搜索/查询意图）自动绑定该工具并 `skip_kb=True`；T2 同样绑定。

### 4.4 新增配置项（settings.py + docker-compose.yml）
| 配置 | 默认 | 说明 |
|---|---|---|
| `ENABLE_WEB_SEARCH` | `true` | 总开关；关 → 完全无联网（零能力回归） |
| `WEB_SEARCH_PROVIDER` | `google` | `google` / `duckduckgo` / `tavily` |
| `WEB_SEARCH_LIMIT` | `5` | 单次返回条数上限 |
| `WEB_SEARCH_API_KEY` | 空 | Tavily 等 keyed provider 用 |
| `WEB_SEARCH_TIMEOUT` | `15` | 单次出网超时（秒） |
| `WEB_SEARCH_CACHE_TTL` | `300` | 只读结果缓存时长（秒） |

### 4.5 安全 / 出网 / 韧性
- 复用 `app.http_client.request_with_fallback`：注入代理不可达自动直连，与媒体下载路径一致。
- 出网域名白名单（`google.com` / `duckduckgo.com` / `tavily.com`），防 SSRF。
- 结果 `snippet` 截断（如 ≤ 300 字/条），防 token 爆炸挤占上下文。
- 失败返回固定提示，**绝不抛异常中断对话**；监控埋点记录调用数/失败率/耗时。

### 4.6 监控与回退
- 日志：`web_search provider=google hits=5 cost=1.2s`；失败记 `web_search failed`。
- 回退：Google 被限流 → 切 `WEB_SEARCH_PROVIDER=duckduckgo`（或 tavily）；一键 `ENABLE_WEB_SEARCH=false` 整体关闭。

## 5. 验证计划
- **单测**（离线）：mock provider，测 `build_web_search_tool` 返回格式、失败降级、缓存命中、`_REALTIME_RE` 对「搜索」走 T1。
- **集成**：真实 `/api/chat-stream` 发「帮我搜一下今天 AI 圈的新闻」，确认返回网页结果、走 T1（日志 `tier=tools`）。
- **回归**：跑 `tests/test_chat_perf_v2.py` 确认 Intent Router / Tool Pool / KB 门控未被破坏。
- **容器**：`docker restart ai-agent-api` 干净启动；确认 import 通过、出网在容器内可达。

## 6. 实施任务分解（若采纳方案 C）
1. `app/web_search.py`：provider 抽象 + Google/DuckDuckGo/Tavily 实现 + `get_provider()`。
2. `app/mcp_tools.py` / `agent.py`：加 `build_web_search_tool()`，接入 `ask_agent` 工具装配。
3. `app/settings.py` + `docker-compose.yml`：暴露 6 个配置项。
4. （方案 B 可选）`app/mcp_client.py`：`StdioMCPClient` + 子进程池 + Dockerfile 加 node。
5. `tests/test_web_search.py`：离线单测。
6. 验证：单测 + 容器重启 + 真实联网冒烟。

## 7. 结论与建议
- **短期最快见效、最稳**：直接做**方案 A**（内置工具），零新增依赖、立刻有联网查询，且天然复用你刚落地的 perf-v2 全套机制。
- **想要「原版博客 server / 任意 stdio MCP」**：补**方案 B**，但需接受容器带 node 的运维成本。
- **推荐方案 C**：A 默认开，B 作为可选扩展，两条路共用同一套路由与缓存。
