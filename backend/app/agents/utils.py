"""agents 模块通用工具集。

本模块提供 agents/ 目录共享的辅助能力：
- 类型规整工具（_coerce_*）
- 提示词模板加载（_load_prompt、_load_ocr_template）
- 文本归一化工具
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

# 使用 TYPE_CHECKING 避免循环导入
if TYPE_CHECKING:
    from .agent_flow import PromptTemplate


# 占位符匹配预编译正则
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


# =============================================================================
# 提示词加载工具
# =============================================================================


def _load_prompt(name: str) -> "PromptTemplate":
    """从 prompts 目录加载提示词模板。

    Args:
        name: 提示词名称（不含扩展名），如 `solver`、`tagger`

    Returns:
        从 `prompts/{name}.md` 加载得到的 PromptTemplate
    """
    # 延迟导入，避免循环依赖
    from .agent_flow import PromptTemplate

    path = Path(__file__).parent / "prompts" / f"{name}.md"
    return PromptTemplate.from_file(path)


def _load_ocr_template() -> "PromptTemplate":
    """加载 OCR 提示词模板，并使用缓存。

    Returns:
        用于 OCR 提取的 PromptTemplate
    """
    # 延迟导入，避免循环依赖
    from .agent_flow import PromptTemplate

    global _OCR_TEMPLATE
    if "_OCR_TEMPLATE" not in globals() or _OCR_TEMPLATE is None:
        path = Path(__file__).parent / "prompts" / "ocr.md"
        _OCR_TEMPLATE = PromptTemplate.from_file(path)
    return _OCR_TEMPLATE


# 初始化 OCR 模板缓存
_OCR_TEMPLATE: PromptTemplate | None = None


# =============================================================================
# 类型规整工具
# =============================================================================


def _coerce_str(value: Any, fallback: str | None = None) -> str | None:
    """将输入值规整为字符串，并支持兜底值。

    Args:
        value: 待规整的值
        fallback: 当输入为 None 时的默认值

    Returns:
        字符串结果或兜底值
    """
    if value is None:
        return fallback
    if isinstance(value, str):
        return _normalize_linebreaks(value)
    return str(value)


def _coerce_str_list(value: object) -> list[str]:
    """将输入值规整为字符串列表。

    Args:
        value: 待规整的值（可为 str、list 或 None）

    Returns:
        字符串列表；输入为空时返回空列表
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
    """将输入值规整为列表，并支持默认回退。

    Args:
        value: 待规整的值
        default: 输入为空时的默认列表

    Returns:
        字符串列表或默认值
    """
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value]
    return default


def _coerce_int(value: Any, default: int, lo: int, hi: int) -> int:
    """将输入值规整为整数，并限制在给定区间。

    Args:
        value: 待规整的值
        default: 转换失败时的默认值
        lo: 最小边界（含）
        hi: 最大边界（含）

    Returns:
        落在 [lo, hi] 的整数值
    """
    try:
        number = int(value)
    except Exception:
        number = default
    return max(lo, min(hi, number))


# =============================================================================
# 文本处理工具
# =============================================================================


def _normalize_linebreaks(text: str) -> str:
    """将换行符统一为 Unix 风格（\\n）。

    Args:
        text: 可能混用多种换行符的输入文本

    Returns:
        换行已统一后的文本
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _contains_placeholder(text: str) -> bool:
    """检查文本中是否包含 `{key}` 占位符。

    Args:
        text: 待检查文本

    Returns:
        找到占位符返回 True，否则返回 False
    """
    return bool(_PLACEHOLDER_RE.search(text))


def _extract_placeholders(text: str) -> list[str]:
    """提取文本中的全部占位符键名。

    Args:
        text: 待提取文本

    Returns:
        占位符键名列表（不含花括号）
    """
    return _PLACEHOLDER_RE.findall(text)
