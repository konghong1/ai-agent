from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document as LCDocument


@dataclass
class ChunkResult:
    """A single chunk produced by a splitter strategy."""
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None  # For parent-child: ID of the parent chunk


@dataclass
class ChunkingConfig:
    """Unified chunking configuration, strategy-agnostic core fields."""
    strategy: str = "recursive_character"
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64
    min_chunk_size_tokens: int = 50
    separators: list[str] = field(
        default_factory=lambda: ["\n\n", "\n", "。", "！", "？", ". ", " ", ""]
    )
    # Per-strategy extras (filled in by factory)
    heading_levels: list[str] = field(default_factory=lambda: ["#", "##", "###"])
    parent_chunk_size_tokens: int = 1024
    child_chunk_size_tokens: int = 256
    child_overlap_tokens: int = 50
    semantic_window_size: int = 3
    semantic_min_chunk_size: int = 100

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkingConfig":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in allowed and v is not None})

    def to_dict(self) -> dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)
