"""
Common utilities for agents module.

This module provides shared utility functions used across agents/ directory:
- Type coercion helpers (_coerce_*)
- Prompt template loading (_load_prompt, _load_ocr_template)
- Text normalization utilities
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Use TYPE_CHECKING to avoid circular import
if TYPE_CHECKING:
    from .agent_flow import PromptTemplate


# Precompiled regex for placeholder matching
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


# =============================================================================
# Prompt Loading Utilities
# =============================================================================

def _load_prompt(name: str) -> "PromptTemplate":
    """Load a prompt template from the prompts directory.
    
    Args:
        name: The prompt name (without extension), e.g., 'solver', 'tagger'
        
    Returns:
        PromptTemplate instance loaded from prompts/{name}.md
    """
    # Lazy import to avoid circular dependency
    from .agent_flow import PromptTemplate
    
    path = Path(__file__).parent / "prompts" / f"{name}.md"
    return PromptTemplate.from_file(path)


def _load_ocr_template() -> "PromptTemplate":
    """Load the OCR prompt template with caching.
    
    Returns:
        PromptTemplate instance for OCR extraction
    """
    # Lazy import to avoid circular dependency
    from .agent_flow import PromptTemplate
    
    global _OCR_TEMPLATE
    if "_OCR_TEMPLATE" not in globals() or _OCR_TEMPLATE is None:
        path = Path(__file__).parent / "prompts" / "ocr.md"
        _OCR_TEMPLATE = PromptTemplate.from_file(path)
    return _OCR_TEMPLATE


# Initialize OCR template cache
_OCR_TEMPLATE: PromptTemplate | None = None


# =============================================================================
# Type Coercion Helpers
# =============================================================================

def _coerce_str(value: Any, fallback: str | None = None) -> str | None:
    """Coerce a value to string with optional fallback.
    
    Args:
        value: The value to coerce
        fallback: Default value if input is None
        
    Returns:
        String representation or fallback
    """
    if value is None:
        return fallback
    if isinstance(value, str):
        return _normalize_linebreaks(value)
    return str(value)


def _coerce_str_list(value: object) -> list[str]:
    """Coerce a value to list of strings.
    
    Args:
        value: The value to coerce (can be str, list, or None)
        
    Returns:
        List of strings, empty list if input is None/empty
    """
    if isinstance(value, list):
        out = []
        for item in value:
            if item is None:
                continue
            out.append(str(item))
        return out
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _coerce_list(value: Any, default: list[str]) -> list[str]:
    """Coerce a value to list with a default fallback.
    
    Args:
        value: The value to coerce
        default: Default list if input is None/empty
        
    Returns:
        List of strings or default
    """
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value]
    return default


def _coerce_int(value: Any, default: int, lo: int, hi: int) -> int:
    """Coerce a value to integer within bounds.
    
    Args:
        value: The value to coerce
        default: Default value if conversion fails
        lo: Minimum bound (inclusive)
        hi: Maximum bound (inclusive)
        
    Returns:
        Integer value clamped to [lo, hi]
    """
    try:
        number = int(value)
    except Exception:
        number = default
    return max(lo, min(hi, number))


# =============================================================================
# Text Processing Utilities
# =============================================================================

def _normalize_linebreaks(text: str) -> str:
    """Normalize line breaks to Unix-style (\\n).
    
    Args:
        text: Input text with potential mixed line breaks
        
    Returns:
        Text with all line breaks normalized to \\n
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _contains_placeholder(text: str) -> bool:
    """Check if text contains any {key} placeholders.
    
    Args:
        text: The text to check
        
    Returns:
        True if placeholders are found, False otherwise
    """
    return bool(_PLACEHOLDER_RE.search(text))


def _extract_placeholders(text: str) -> list[str]:
    """Extract all placeholder keys from text.
    
    Args:
        text: The text to extract placeholders from
        
    Returns:
        List of placeholder keys (without braces)
    """
    return _PLACEHOLDER_RE.findall(text)
