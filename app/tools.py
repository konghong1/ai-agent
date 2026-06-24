from __future__ import annotations

import ast
import operator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain_core.tools import tool


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Only numeric expressions are allowed.")


@tool
def calculator(expression: str) -> str:
    """Calculate a numeric expression. Supports +, -, *, /, //, %, ** and parentheses."""
    tree = ast.parse(expression, mode="eval")
    return str(_safe_eval(tree))


@tool
def current_time(timezone: str = "Asia/Shanghai") -> str:
    """Get the current date and time for an IANA timezone, for example Asia/Shanghai or America/New_York."""
    now = datetime.now(ZoneInfo(timezone))
    return now.isoformat(timespec="seconds")


@tool
def list_workspace_files(max_files: int = 50) -> str:
    """List files in the local project workspace."""
    max_files = max(1, min(max_files, 200))
    files = [
        str(path.relative_to(WORKSPACE_ROOT))
        for path in WORKSPACE_ROOT.rglob("*")
        if path.is_file() and ".venv" not in path.parts and "__pycache__" not in path.parts
    ]
    return "\n".join(sorted(files)[:max_files]) or "No files found."


@tool
def read_workspace_text_file(relative_path: str, max_chars: int = 4000) -> str:
    """Read a UTF-8 text file from the local workspace using a relative path."""
    max_chars = max(1, min(max_chars, 12000))
    target = (WORKSPACE_ROOT / relative_path).resolve()
    if not target.is_relative_to(WORKSPACE_ROOT):
        raise ValueError("Path must stay inside the workspace.")
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    return target.read_text(encoding="utf-8", errors="replace")[:max_chars]


# ============================================================
# Knowledge Base Search Tool (Task 12)
# ============================================================

@tool
def search_knowledge_base(query: str, kb_id: int | None = None, top_k: int = 5) -> str:
    """Search one or all knowledge bases for relevant information.

    Args:
        query: The search query text.
        kb_id: Optional specific knowledge base ID to search. If None, searches all KBs.
        top_k: Number of results to return (1-20).

    Returns:
        Formatted search results with document names, folder paths, and relevant text snippets.
    """
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.models import KnowledgeBase
    from app.services import KnowledgeBaseService

    db = SessionLocal()
    try:
        if kb_id:
            kbs = [db.get(KnowledgeBase, kb_id)]
        else:
            kbs = list(db.scalars(select(KnowledgeBase).where(KnowledgeBase.enabled == True)).all())

        if not kbs or kbs[0] is None:
            return "未找到可用的知识库。"

        all_results = []
        for kb in kbs:
            hits = KnowledgeBaseService.search_knowledge_base(db, kb.id, query, top_k=top_k)
            for hit in hits:
                hit["_kb_name"] = kb.name
            all_results.extend(hits)

        if not all_results:
            return "未在知识库中找到相关内容。"

        lines = ["知识库搜索结果：", ""]
        for i, hit in enumerate(all_results, 1):
            lines.append(f"--- 结果 {i} ---")
            lines.append(f"知识库: {hit.get('_kb_name', '')}")
            lines.append(f"文档: {hit.get('document_name', '')}")
            path = hit.get('folder_path', '')
            if path:
                lines.append(f"路径: {path}")
            lines.append(f"相关度: {hit.get('score', 0):.2%}")
            content = hit.get('content', '')
            if len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"内容: {content}")
            lines.append("")

        return "\n".join(lines)

    finally:
        db.close()


def get_tools():
    """Return all available LangChain tools."""
    return [calculator, current_time, list_workspace_files, read_workspace_text_file, search_knowledge_base]
