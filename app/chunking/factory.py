from __future__ import annotations

from app.chunking.strategies import (
    RecursiveCharacterChunker,
    FixedSizeChunker,
    HierarchicalChunker,
)
from app.chunking.base import ChunkingConfig, ChunkResult

# Registry: strategy_name -> (class, file_types)
STRATEGY_REGISTRY: dict[str, type] = {
    "recursive_character": RecursiveCharacterChunker,
    "fixed_size": FixedSizeChunker,
    "hierarchical": HierarchicalChunker,
}

# Supported file types per strategy
STRATEGY_FILE_SUPPORT: dict[str, list[str]] = {
    "recursive_character": ["pdf", "docx", "txt", "markdown", "csv", "json", "code"],
    "fixed_size": ["pdf", "docx", "txt", "markdown", "csv", "json", "code"],
    "hierarchical": ["markdown", "txt", "pdf", "docx"],
}


def get_chunker(strategy: str):
    """Return a chunker instance for the given strategy name."""
    cls = STRATEGY_REGISTRY.get(strategy)
    if not cls:
        raise ValueError(
            f"Unknown chunking strategy: {strategy}. "
            f"Available: {list(STRATEGY_REGISTRY.keys())}"
        )
    return cls()


def chunk_text(text: str, strategy: str, config: dict, metadata: dict | None = None) -> list[dict]:
    """Public entry point: chunk text using the configured strategy.

    Returns list of dicts: [{\"content\": ..., \"metadata\": ...}, ...]
    """
    cfg = ChunkingConfig.from_dict(config or {})
    cfg.strategy = strategy
    chunker = get_chunker(strategy)
    metadata = metadata or {}
    results = chunker.split(text, cfg, metadata)
    return [{"content": r.content, "metadata": r.metadata} for r in results]


def list_strategies() -> list[dict]:
    """Return metadata about all available strategies."""
    strategies = []
    for name, cls in STRATEGY_REGISTRY.items():
        support = STRATEGY_FILE_SUPPORT.get(name, [])
        doc = {
            "value": name,
            "label": _strategy_label(name),
            "description": _strategy_desc(name),
            "supported_file_types": support,
        }
        strategies.append(doc)
    return strategies


def _strategy_label(name: str) -> str:
    labels = {
        "recursive_character": "递归字符分块（推荐）",
        "fixed_size": "固定大小分块",
        "hierarchical": "文档结构分块",
    }
    return labels.get(name, name)


def _strategy_desc(name: str) -> str:
    descs = {
        "recursive_character": "按分隔符优先级递归切分，优先在段落边界切割，保留语义完整性。生产环境默认推荐。",
        "fixed_size": "按固定 token 数强制切割，计算成本最低，适合格式均匀的日志或导出数据。",
        "hierarchical": "按 Markdown 标题层级切分，每个 chunk 对应一个章节，适合结构化文档。",
    }
    return descs.get(name, "")
