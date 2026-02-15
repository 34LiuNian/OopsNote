from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import logging
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..clients import AIClient
from ..models import ProblemBlock, SolutionBlock, TaggingResult, TaskCreateRequest
from ..tags import TagDimension, tag_store

logger = logging.getLogger(__name__)


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_CHEMFIG_RE = re.compile(r"\\chemfig|chemfig", re.IGNORECASE)
_CHEM_HINT_RE = re.compile(r"化学|有机|结构式|分子式|反应", re.IGNORECASE)


@dataclass
class PromptTemplate:
    name: str
    system_prompt: str
    user_template: str

    @classmethod
    def from_file(cls, path: Path) -> "PromptTemplate":
        raw = path.read_text(encoding="utf-8")
        if "USER:" not in raw:
            raise ValueError(f"Prompt file {path} must contain a 'USER:' section")
        system_part, user_part = raw.split("USER:", 1)
        system_text = system_part.replace("SYSTEM:", "", 1)
        return cls(
            name=path.stem,
            system_prompt=system_text.strip(),
            user_template=user_part.strip(),
        )

    def render(self, context: Mapping[str, Any]) -> tuple[str, str]:
        """Render prompts by replacing `{key}` placeholders only.

        We intentionally do NOT use `str.format` because prompt files include JSON examples
        that contain `{`/`}` which would otherwise be interpreted as formatting braces.
        """

        def substitute(text: str) -> str:
            def repl(match: re.Match[str]) -> str:
                key = match.group(1)
                value = context.get(key, "")
                return "" if value is None else str(value)

            return _PLACEHOLDER_RE.sub(repl, text)

        return substitute(self.system_prompt), substitute(self.user_template)


@dataclass
class AgentResult:
    name: str
    output: dict[str, Any]
    raw_text: str


class LLMAgent:
    """Lightweight agent wrapper that keeps prompts and parsing localized."""

    def __init__(
        self,
        name: str,
        client: AIClient,
        template: PromptTemplate,
        required_keys: Sequence[str] | None = None,
        model_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.name = name
        self.client = client
        self.template = template
        self.required_keys = list(required_keys or [])
        self.model_resolver = model_resolver

    def run(
        self, context: Mapping[str, Any]
    ) -> AgentResult:
        system_prompt, user_prompt = self.template.render(context)
        thinking = context.get("agent_thinking")

        override = None
        if self.model_resolver:
            override = self.model_resolver(self.name)
            if override:
                self.client.model = override

        try:
            if "image_bytes" in context:
                output = self.client.structured_chat_with_image(
                    system_prompt,
                    user_prompt,
                    image_bytes=context["image_bytes"],
                    mime_type=context.get("mime_type", "image/jpeg"),
                    thinking=thinking if isinstance(thinking, bool) else None,
                )
            else:
                output = self.client.structured_chat(
                    system_prompt,
                    user_prompt,
                    thinking=thinking if isinstance(thinking, bool) else None,
                )
        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            output = {}

        return AgentResult(
            name=self.name,
            output=output,
            raw_text="",
        )


class AgentOrchestrator:
    """Sequential multi-agent flow: solver -> tagger."""

    def __init__(
        self,
        solver: LLMAgent,
        tagger: LLMAgent,
        is_enabled: Callable[[str], bool] | None = None,
        thinking_resolver: Callable[[str], bool] | None = None,
    ) -> None:
        self.solver = solver
        self.tagger = tagger
        self.is_enabled = is_enabled
        self.thinking_resolver = thinking_resolver

    def solve_and_tag(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
    ) -> tuple[list[SolutionBlock], list[TaggingResult]]:
        solutions: list[SolutionBlock] = []
        tags: list[TaggingResult] = []
        for problem in problems:
            context = self._build_context(payload, problem)

            def _set_thinking(agent_key: str) -> None:
                if self.thinking_resolver is None:
                    context["agent_thinking"] = True
                    return
                try:
                    context["agent_thinking"] = bool(self.thinking_resolver(agent_key))
                except Exception:
                    context["agent_thinking"] = True

            _set_thinking("SOLVER")
            solve = self.solver.run(context).output
            context.update({k: v for k, v in solve.items() if v is not None})
            solutions.append(
                SolutionBlock(
                    problem_id=problem.problem_id,
                    answer=str(solve.get("answer", "")),
                    explanation=str(solve.get("explanation", "")),
                    short_answer=solve.get("short_answer") or None,
                )
            )

            _set_thinking("TAGGER")
            tag_payload = self.tagger.run(context).output
            tags.append(self._to_tagging(problem.problem_id, tag_payload))
        return solutions, tags

    @staticmethod
    def _build_context(
        payload: TaskCreateRequest, problem: ProblemBlock
    ) -> dict[str, Any]:
        latex = "\n".join(problem.latex_blocks)
        skills: list[str] = []
        if _needs_chemfig_skill(problem, latex):
            skills.append("chemfig")
        knowledge_candidates = tag_store.list(
            dimension=TagDimension.KNOWLEDGE, limit=200
        )
        error_candidates = tag_store.list(dimension=TagDimension.ERROR, limit=200)
        meta_candidates = tag_store.list(dimension=TagDimension.META, limit=200)

        def _render_candidates(items: list[Any]) -> str:
            if not items:
                return ""
            return "\n".join(f"- {getattr(item, 'value', str(item))}" for item in items)

        return {
            "subject": payload.subject,
            "grade": payload.grade or "",
            "notes": payload.notes or "",
            "problem_text": problem.problem_text,
            "latex": latex,
            "source": problem.source or "",
            "skills": skills,
            "manual_knowledge_tags": "、".join(
                [t for t in (payload.knowledge_tags or []) if str(t).strip()]
            ),
            "manual_error_tags": "、".join(
                [t for t in (payload.error_tags or []) if str(t).strip()]
            ),
            "manual_source": (payload.source or "").strip(),
            "knowledge_candidates": _render_candidates(knowledge_candidates),
            "error_candidates": _render_candidates(error_candidates),
            "meta_candidates": _render_candidates(meta_candidates),
        }

    @staticmethod
    def _to_tagging(problem_id: str, data: Mapping[str, Any]) -> TaggingResult:
        return TaggingResult(
            problem_id=problem_id,
            knowledge_points=_coerce_list(
                data.get("knowledge_points"), default=["未标注"]
            ),
            question_type=str(data.get("question_type", "解答题")),
            skills=_coerce_list(data.get("skills"), default=["分析推理"]),
            error_hypothesis=_coerce_list(
                data.get("error_hypothesis"), default=["待复盘"]
            ),
            recommended_actions=_coerce_list(
                data.get("recommended_actions"), default=["完成 2 道同类题"]
            ),
        )


def _load_skill(agent_name: str, name: str) -> str:
    cache_key = f"{agent_name.lower()}::{name}"
    if cache_key in _SKILL_CACHE:
        return _SKILL_CACHE[cache_key]
    path = _SKILL_DIR / agent_name.lower() / f"{name}.txt"
    if not path.exists():
        _SKILL_CACHE[cache_key] = ""
        return ""
    text = path.read_text(encoding="utf-8").strip()
    _SKILL_CACHE[cache_key] = text
    return text


def _needs_chemfig_skill(problem: ProblemBlock, latex: str) -> bool:
    if _CHEMFIG_RE.search(latex or ""):
        return True
    if _CHEMFIG_RE.search(problem.problem_text or ""):
        return True
    if _CHEM_HINT_RE.search(problem.problem_text or ""):
        return True
    for opt in problem.options or []:
        text = getattr(opt, "text", "") or ""
        if _CHEMFIG_RE.search(text) or _CHEM_HINT_RE.search(text):
            return True
        for block in getattr(opt, "latex_blocks", []) or []:
            if _CHEMFIG_RE.search(block):
                return True
    return False


def _coerce_list(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value]
    return default


def _coerce_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(lo, min(hi, number))
