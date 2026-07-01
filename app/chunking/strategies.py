from __future__ import annotations

import logging
from typing import Any

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    CharacterTextSplitter,
)
from langchain_core.documents import Document as LCDocument

from app.chunking.base import ChunkResult, ChunkingConfig

logger = logging.getLogger(__name__)


def _build_langchain_docs(
    text: str, metadata: dict, page_numbers: list[int] | None = None
) -> list[LCDocument]:
    """Wrap raw text into LangChain Document objects."""
    if page_numbers:
        return [
            LCDocument(page_content=text, metadata={**metadata, "page": pn})
            for pn in page_numbers
        ]
    return [LCDocument(page_content=text, metadata=metadata)]


class RecursiveCharacterChunker:
    """Production-default: recursive character splitting with token-aware sizing.

    Splits by separators recursively, respecting token limits via tiktoken.
    """

    def split(self, text: str, config: ChunkingConfig, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        metadata = metadata or {}
        sep = config.separators
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size_tokens,
            chunk_overlap=config.chunk_overlap_tokens,
            separators=sep,
            
        )
        docs = splitter.create_documents([text], metadatas=[metadata])
        return [ChunkResult(content=d.page_content, metadata=d.metadata or {}) for d in docs]


class FixedSizeChunker:
    """Fixed-size character splitting. Fast but semantically rough."""

    def split(self, text: str, config: ChunkingConfig, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        metadata = metadata or {}
        splitter = CharacterTextSplitter(
            separator="",
            chunk_size=config.chunk_size_tokens,
            chunk_overlap=config.chunk_overlap_tokens,
            is_separator_regex=False,
        )
        docs = splitter.create_documents([text], metadatas=[metadata])
        return [ChunkResult(content=d.page_content, metadata=d.metadata or {}) for d in docs]


class HierarchicalChunker:
    """Document-structure chunking: splits by headings, then falls back to recursive.

    Best for Markdown / technical docs with clear heading hierarchy.
    """

    def split(self, text: str, config: ChunkingConfig, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        metadata = metadata or {}
        # Try splitting by heading levels
        import re
        heading_pattern = re.compile(
            r'^(#{1,' + str(len(config.heading_levels)) + r'})\s+(.+)$',
            re.MULTILINE,
        )

        lines = text.split('\n')
        sections: list[tuple[str, str, dict]] = []  # (heading, content, meta)
        current_heading = ""
        current_lines: list[str] = []

        for line in lines:
            m = heading_pattern.match(line.strip())
            if m:
                if current_lines:
                    content = '\n'.join(current_lines).strip()
                    if content:
                        sections.append((current_heading, content, {**metadata}))
                current_heading = line.strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            content = '\n'.join(current_lines).strip()
            if content:
                sections.append((current_heading, content, {**metadata}))

        if not sections:
            # Fallback to recursive
            return RecursiveCharacterChunker().split(text, config, metadata)

        # Further split oversized sections recursively
        results: list[ChunkResult] = []
        recursive = RecursiveCharacterChunker()
        for heading, content, meta in sections:
            token_count = _token_count(content)
            if token_count <= config.chunk_size_tokens:
                meta["heading"] = heading
                results.append(ChunkResult(content=content, metadata=meta))
            else:
                sub_chunks = recursive.split(content, config, {**meta, "heading": heading})
                results.extend(sub_chunks)

        return results


def _token_count(text: str) -> int:
    """Approximate token count using tiktoken (openai tokenizer)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text, disallowed_special=set()))
    except Exception:
        # Fallback: rough estimate 1 token ~= 3.5 chars for Chinese, 4 for English
        return max(1, len(text) // 3)
