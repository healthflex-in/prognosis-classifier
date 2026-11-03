"""Normalise LangChain message content to plain text.

Older Gemini models return ``content`` as a str. Gemini 3.x returns a list of
content blocks (text blocks, plus thinking/signature blocks), so callers that
do ``response.content.strip()`` break.
"""
from typing import Any


def message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                parts.append(block.get("text") or "")
        return "".join(parts)
    return "" if content is None else str(content)
