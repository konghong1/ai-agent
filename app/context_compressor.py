"""Context compression utilities for managing conversation length."""

import logging
from typing import Any, Tuple

from app.token_counter import TokenCounter, TokenUsage

logger = logging.getLogger(__name__)


class ContextCompressor:
    """Compress conversation history when approaching token limits."""

    # Compression threshold (80% of max context)
    COMPRESS_THRESHOLD = 0.80

    # Target ratio after compression (50% of max context)
    TARGET_RATIO = 0.50

    # Keep last N turns of conversation (1 turn = user + assistant)
    KEEP_RECENT_TURNS = 4

    # Summary prompt template
    SUMMARY_PROMPT = """请用简洁的语言总结以下对话的关键信息（不超过200字）：

{conversation}

摘要："""

    def __init__(self, llm, token_counter: TokenCounter):
        """Initialize compressor with LLM and token counter."""
        self.llm = llm
        self.token_counter = token_counter

    def should_compress(
        self, usage: TokenUsage, threshold: float = None
    ) -> bool:
        """Check if compression is needed based on usage ratio."""
        threshold = threshold or self.COMPRESS_THRESHOLD
        ratio = usage.usage_ratio
        should = ratio >= threshold

        if should:
            logger.info(
                "Context usage %.1f%% >= threshold %.1f%%, compression needed",
                ratio * 100, threshold * 100
            )

        return should

    def compress_messages(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[Any],
    ) -> Tuple[list[dict], str]:
        """
        Compress conversation history by summarizing old turns.

        Args:
            messages: Full conversation history
            system_prompt: Original system prompt
            tools: Tool definitions

        Returns:
            (compressed_messages, summary_text)
        """
        # Filter conversation messages (exclude system)
        conversation_msgs = [
            m for m in messages
            if m.get("role") in ("user", "assistant", "tool")
        ]

        # If too few messages, no need to compress
        min_msgs = self.KEEP_RECENT_TURNS * 2
        if len(conversation_msgs) <= min_msgs:
            logger.info(
                "Only %d conversation messages, skipping compression",
                len(conversation_msgs)
            )
            return messages, ""

        # Split into old and recent
        recent_msgs = conversation_msgs[-min_msgs:]
        old_msgs = conversation_msgs[:-min_msgs]

        logger.info(
            "Compressing %d old messages, keeping %d recent",
            len(old_msgs), len(recent_msgs)
        )

        # Generate summary of old messages
        summary = self._summarize(old_msgs)

        # Reconstruct messages
        compressed = []

        # Original system prompt
        if system_prompt:
            compressed.append({"role": "system", "content": system_prompt})

        # Inject summary as system context
        if summary:
            compressed.append({
                "role": "system",
                "content": f"[历史对话摘要]\n{summary}\n\n请基于此继续对话。"
            })

        # Recent conversation
        compressed.extend(recent_msgs)

        # Calculate compression ratio
        old_tokens = self.token_counter.count_messages(old_msgs)
        summary_tokens = self.token_counter.count_text(summary)
        compression_ratio = (old_tokens - summary_tokens) / old_tokens if old_tokens > 0 else 0

        logger.info(
            "Context compressed: %d -> %d messages, saved %d tokens (%.1f%%)",
            len(messages), len(compressed),
            old_tokens - summary_tokens,
            compression_ratio * 100
        )

        return compressed, summary

    def _summarize(self, messages: list[dict]) -> str:
        """Generate summary of old conversation messages."""
        if not messages:
            return ""

        # Format conversation for summarization
        lines = []
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, str):
                lines.append(f"{role}: {content}")
            elif isinstance(content, list):
                # Extract text from multimodal content
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        lines.append(f"{role}: {part['text']}")

        conversation_text = "\n".join(lines)

        # Truncate if too long (avoid token limit in summarization)
        max_chars = 8000
        if len(conversation_text) > max_chars:
            conversation_text = conversation_text[:max_chars] + "\n...(已截断)"

        # Call LLM for summarization
        prompt = self.SUMMARY_PROMPT.format(conversation=conversation_text)

        try:
            response = self.llm.invoke(prompt)
            summary = response.content if hasattr(response, 'content') else str(response)
            logger.info("Generated summary: %d chars", len(summary))
            return summary
        except Exception as e:
            logger.warning("Summarization failed: %s, using fallback", e)
            # Fallback: extract first 200 chars of each message
            fallback_parts = []
            for m in messages[:5]:  # Max 5 old messages
                content = m.get("content", "")
                if isinstance(content, str) and content:
                    fallback_parts.append(content[:100])
            return "历史对话要点：" + "；".join(fallback_parts) if fallback_parts else ""
