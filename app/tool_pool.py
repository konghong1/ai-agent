"""
Tool Pool - Unified Tool Caching System

Manages tool loading and caching for:
- MCP tools (remote servers)
- Skills (local/remote skill definitions)
- Knowledge base (retrieve_knowledge tool)

Design principles:
- First load: build tools + cache
- Subsequent loads: return cached tools
- Invalidation: on config change
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import StructuredTool
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Tool Pool Cache
# ═══════════════════════════════════════════════════════════

@dataclass
class ToolPoolEntry:
    """Cached tool pool entry for a user."""
    tools: list[StructuredTool]
    mcp_count: int = 0
    skill_count: int = 0
    has_knowledge_tool: bool = False
    loaded_at: datetime = field(default_factory=datetime.utcnow)
    config_hash: str = ""


class ToolPool:
    """
    Unified tool pool with caching.
    
    Features:
    - MCP tools: loaded from remote servers (connection + schema)
    - Skills: loaded from local/remote definitions
    - Knowledge: retrieve_knowledge tool (on-demand RAG)
    - Caching: first load caches, subsequent loads return cached
    - Invalidation: on config change or manual clear
    """
    
    _instance: Optional['ToolPool'] = None
    _cache: dict[int, ToolPoolEntry] = {}
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_tools(cls, user_id: int, db: Session, agent_id: int = None) -> list[StructuredTool]:
        """
        Get tools for a user (from cache or load fresh).
        
        Args:
            user_id: User ID
            db: Database session
            agent_id: Optional agent ID (for agent-specific tools)
        
        Returns:
            List of StructuredTool instances
        """
        cache_key = user_id
        
        # Check cache
        with cls._lock:
            entry = cls._cache.get(cache_key)
            if entry:
                # Verify config hasn't changed
                current_hash = cls._compute_config_hash(user_id, db)
                if current_hash == entry.config_hash:
                    logger.info(f"ToolPool cache HIT for user {user_id} ({len(entry.tools)} tools)")
                    return entry.tools
                else:
                    logger.info(f"ToolPool cache STALE for user {user_id}, reloading...")
        
        # Load fresh
        tools = cls._load_tools(user_id, db, agent_id)
        
        # Cache
        config_hash = cls._compute_config_hash(user_id, db)
        entry = ToolPoolEntry(
            tools=tools,
            config_hash=config_hash,
        )
        
        with cls._lock:
            cls._cache[cache_key] = entry
        
        logger.info(f"ToolPool loaded {len(tools)} tools for user {user_id} (mcp={entry.mcp_count}, skill={entry.skill_count})")
        return tools
    
    @classmethod
    def invalidate(cls, user_id: int = None, reason: str = "config changed"):
        """
        Invalidate tool pool cache.
        
        Args:
            user_id: Specific user to invalidate, or None for all
            reason: Reason for invalidation (logging)
        """
        with cls._lock:
            if user_id:
                cls._cache.pop(user_id, None)
                logger.info(f"ToolPool invalidated for user {user_id}: {reason}")
            else:
                cls._cache.clear()
                logger.info(f"ToolPool invalidated globally: {reason}")
        
        # Trigger hook
        from app.hooks import trigger_hooks
        trigger_hooks("ToolPoolInvalidated", user_id, reason)
    
    @classmethod
    def _load_tools(cls, user_id: int, db: Session, agent_id: int = None) -> list[StructuredTool]:
        """
        Load all tools for a user.
        
        Order:
        1. MCP tools (remote servers)
        2. Skills
        3. Knowledge base tool
        4. Trigger ToolInit hook
        """
        tools = []
        
        # 1. MCP tools
        mcp_tools = cls._load_mcp_tools(user_id, db)
        tools.extend(mcp_tools)
        mcp_count = len(mcp_tools)
        
        # 2. Skills
        skill_tools = cls._load_skill_tools(user_id, db)
        tools.extend(skill_tools)
        skill_count = len(skill_tools)
        
        # 3. Knowledge base tool
        kb_tool = cls._make_retrieve_knowledge_tool(user_id, db, agent_id)
        if kb_tool:
            tools.append(kb_tool)
        
        # 4. ToolInit hook
        from app.hooks import trigger_hooks
        trigger_hooks("ToolInit", user_id, tools, db)
        
        # Update entry stats
        if user_id in cls._cache:
            cls._cache[user_id].mcp_count = mcp_count
            cls._cache[user_id].skill_count = skill_count
            cls._cache[user_id].has_knowledge_tool = kb_tool is not None
        
        return tools
    
    @classmethod
    def _load_mcp_tools(cls, user_id: int, db: Session) -> list[StructuredTool]:
        """Load MCP tools from remote servers."""
        from app.mcp_tools import build_mcp_langchain_tools
        try:
            start_time = time.time()
            tools = build_mcp_langchain_tools(db, user_id)
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Loaded {len(tools)} MCP tools for user {user_id} in {elapsed_ms}ms")
            return tools
        except Exception as e:
            logger.error(f"Failed to load MCP tools: {e}")
            return []
    
    @classmethod
    def _load_skill_tools(cls, user_id: int, db: Session) -> list[StructuredTool]:
        """Load skill tools from database."""
        from app.models import Skill
        
        tools = []
        try:
            skills = db.scalars(
                select(Skill).where(
                    Skill.user_id == user_id,
                    Skill.enabled == True,
                )
            ).all()
            
            for skill in skills:
                tool = cls._skill_to_tool(skill)
                if tool:
                    tools.append(tool)
            
            logger.info(f"Loaded {len(tools)} skill tools for user {user_id}")
            return tools
        except Exception as e:
            logger.error(f"Failed to load skill tools: {e}")
            return tools
    
    @classmethod
    def _skill_to_tool(cls, skill) -> Optional[StructuredTool]:
        """Convert a Skill model to StructuredTool."""
        from app.mcp_tools import _build_args_model
        
        try:
            # Parse skill content for parameters
            # TODO: Parse SKILL.md format for tool schema
            args_schema = _build_args_model({
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Input for the skill",
                    }
                },
                "required": ["input"],
            })
            
            def _run(input: str, skill_id=skill.id) -> str:
                from app.core.database import SessionLocal
                from app.agent_loop import TOOL_HANDLERS
                
                db2 = SessionLocal()
                try:
                    # Look for registered handler
                    handler_name = f"skill_{skill.name}"
                    if handler_name in TOOL_HANDLERS:
                        return TOOL_HANDLERS[handler_name](input)
                    
                    # Fallback: return skill content as prompt
                    sk = db2.get(type(skill), skill_id)
                    if sk and sk.content:
                        return f"Skill '{sk.name}': {sk.content[:500]}"
                    return f"Skill '{skill.name}' (no content)"
                finally:
                    db2.close()
            
            return StructuredTool(
                name=f"skill_{skill.name}",
                description=skill.description or f"Skill: {skill.title or skill.name}",
                args_schema=args_schema,
                func=_run,
            )
        except Exception as e:
            logger.error(f"Failed to convert skill {skill.name} to tool: {e}")
            return None
    
    @classmethod
    def _make_retrieve_knowledge_tool(cls, user_id: int, db: Session, agent_id: int = None) -> Optional[StructuredTool]:
        """
        Create retrieve_knowledge tool for on-demand RAG.
        
        Replaces unconditional RAG with model-driven knowledge retrieval.
        """
        from app.mcp_tools import _build_args_model
        from app.settings import get_settings
        
        settings = get_settings()
        
        # Check if knowledge base is enabled
        if not getattr(settings, "enable_knowledge_tool", True):
            return None
        
        # Check if user has any knowledge bases
        from app.models import KnowledgeBase, AgentKnowledgeBase
        
        has_kb = db.scalar(
            select(KnowledgeBase.id).where(
                KnowledgeBase.user_id == user_id,
                KnowledgeBase.enabled == True,
            ).limit(1)
        )
        
        if not has_kb and not agent_id:
            return None
        
        def _run(query: str) -> str:
            from app.core.database import SessionLocal
            from app.services import HybridRetriever, ContextBuilder
            
            db2 = SessionLocal()
            try:
                # Find user's knowledge bases
                kbs = list(db2.scalars(
                    select(KnowledgeBase).where(
                        KnowledgeBase.user_id == user_id,
                        KnowledgeBase.enabled == True,
                    )
                ))
                
                if not kbs:
                    return "（未找到启用的知识库）"
                
                # Search across all KBs
                all_hits = []
                for kb in kbs:
                    retriever = HybridRetriever(kb, db2)
                    hits = retriever.retrieve(query=query, top_k=10)
                    for h in hits:
                        h['metadata']['kb_name'] = kb.name
                    all_hits.extend(hits)
                
                if not all_hits:
                    return "（知识库无相关内容）"
                
                # Build context
                all_hits.sort(key=lambda x: x.get('score', 0), reverse=True)
                builder = ContextBuilder(max_tokens=4000)
                context, _ = builder.build(query=query, hits=all_hits[:10])
                
                return context
            except Exception as e:
                logger.error(f"retrieve_knowledge failed: {e}")
                return f"检索失败: {str(e)}"
            finally:
                db2.close()
        
        args_schema = _build_args_model({
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索语句，用于查找相关知识、历史偏好或过往讨论",
                }
            },
            "required": ["query"],
        })
        
        return StructuredTool(
            name="retrieve_knowledge",
            description=(
                "当回答需要以下信息时调用：\n"
                "1. 用户的历史偏好或过往讨论\n"
                "2. 产品文档、技术规范、API 文档\n"
                "3. 领域知识、业务规则\n"
                "输入：检索语句；输出：相关内容摘要"
            ),
            args_schema=args_schema,
            func=_run,
        )
    
    @classmethod
    def _compute_config_hash(cls, user_id: int, db: Session) -> str:
        """
        Compute a hash of current tool configuration.
        
        Used to detect config changes and invalidate cache.
        """
        import hashlib
        from app.models import McpServer, Skill
        
        parts = []
        
        # MCP servers
        servers = list(db.scalars(
            select(McpServer.id, McpServer.name, McpServer.enabled, McpServer.tool_allowlist).where(
                McpServer.user_id == user_id,
            )
        ))
        for s in servers:
            parts.append(f"mcp:{s.id}:{s.name}:{s.enabled}:{','.join(sorted(s.tool_allowlist or []))}")
        
        # Skills
        skills = list(db.scalars(
            select(Skill.id, Skill.name, Skill.enabled).where(
                Skill.user_id == user_id,
            )
        ))
        for s in skills:
            parts.append(f"skill:{s.id}:{s.name}:{s.enabled}")
        
        payload = "|".join(parts)
        return hashlib.md5(payload.encode()).hexdigest()
    
    @classmethod
    def get_stats(cls) -> dict:
        """
        Get tool pool statistics.
        
        Returns:
            Dict with cache size, user counts, etc.
        """
        with cls._lock:
            return {
                "cache_size": len(cls._cache),
                "users": [
                    {
                        "user_id": uid,
                        "tools": len(entry.tools),
                        "mcp_count": entry.mcp_count,
                        "skill_count": entry.skill_count,
                        "has_knowledge_tool": entry.has_knowledge_tool,
                        "loaded_at": entry.loaded_at.isoformat(),
                    }
                    for uid, entry in cls._cache.items()
                ],
            }


# ═══════════════════════════════════════════════════════════
#  Convenience Functions
# ═══════════════════════════════════════════════════════════

def get_tool_pool() -> ToolPool:
    """Get singleton ToolPool instance."""
    return ToolPool()


def invalidate_tool_pool(user_id: int = None, reason: str = "config changed"):
    """Invalidate tool pool cache."""
    ToolPool.invalidate(user_id, reason)
