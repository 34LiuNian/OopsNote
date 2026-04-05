from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..clients import AIClient
from ..config.subjects import SUBJECTS
from ..models import ProblemBlock, SolutionBlock, TaggingResult, TaskCreateRequest
from ..tags import TagDimension, tag_store
from . import utils

logger = logging.getLogger(__name__)

# Skill 缓存与目录
_SKILL_CACHE: dict[str, str] = {}
_SKILL_DIR = Path(__file__).parent.parent / "skills"

# 本地保留 chemfig 检测正则（领域特化逻辑）
_CHEMFIG_RE = re.compile(r"\\chemfig|chemfig", re.IGNORECASE)
_CHEM_HINT_RE = re.compile(r"化学|有机|结构式|分子式|反应", re.IGNORECASE) # TODO: 优化识别方式


def _tag_sort_key(item: Any) -> tuple[int, str]:
    return (-int(getattr(item, "ref_count", 0) or 0), str(getattr(item, "value", "")))


def _pick_tag_candidates(
    dimension: TagDimension,
    *,
    subject: str | None = None,
    limit: int = 200,
) -> list[Any]:
    items = tag_store.list(dimension=dimension, limit=max(limit * 12, 2000))
    items.sort(key=_tag_sort_key)

    if dimension != TagDimension.KNOWLEDGE:
        return items[:limit]

    subject_label = SUBJECTS.get(subject or "", "")
    if not subject_label:
        return []

    prefix = f"{subject_label}/"
    subject_specific: list[Any] = []

    for item in items:
        item_subject = str(getattr(item, "subject", "") or "").strip()
        if item_subject and item_subject == (subject or ""):
            subject_specific.append(item)
            continue

        aliases = [str(alias).strip() for alias in (getattr(item, "aliases", []) or []) if str(alias).strip()]
        if str(getattr(item, "value", "")).startswith(prefix) or any(
            alias.startswith(prefix) for alias in aliases
        ):
            subject_specific.append(item)

    return subject_specific[:limit]


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
        """渲染提示词，仅替换 `{key}` 占位符。

        这里有意不使用 `str.format`，因为提示词文件里包含 JSON 示例，
        其中的 `{`/`}` 会被误判为格式化占位符。
        """

        def substitute(text: str) -> str:
            def repl(match: re.Match[str]) -> str:
                key = match.group(1)
                value = context.get(key, "")
                return "" if value is None else str(value)

            return utils._PLACEHOLDER_RE.sub(repl, text)

        return substitute(self.system_prompt), substitute(self.user_template)


@dataclass
class AgentResult:
    name: str
    output: dict[str, Any]
    raw_text: str


class LLMAgent:
    """轻量 Agent 包装器，局部封装提示词与解析逻辑。"""

    def __init__(
        self,
        name: str,
        client: AIClient,
        template: PromptTemplate,
        required_keys: Sequence[str] | None = None,
        model_resolver: Callable[[str], str | None] | None = None,
        temperature_resolver: Callable[[str], float | None] | None = None,
    ) -> None:
        self.name = name
        self.client = client
        self.template = template
        self.required_keys = list(required_keys or [])
        self.model_resolver = model_resolver
        self.temperature_resolver = temperature_resolver

    def run(self, context: Mapping[str, Any]) -> AgentResult:
        system_prompt, user_prompt = self.template.render(context)
        thinking = context.get("agent_thinking")

        override = None
        if self.model_resolver:
            override = self.model_resolver(self.name)
            if override:
                self.client.model = override

        # 若存在配置，则应用 Agent 级温度覆盖
        if self.temperature_resolver:
            temp_override = self.temperature_resolver(self.name)
            if temp_override is not None:
                self.client.temperature = temp_override

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
        except Exception as exc:
            logger.exception("Agent %s failed", self.name)
            raise RuntimeError(f"Agent {self.name} failed") from exc

        if not isinstance(output, dict):
            raise RuntimeError(
                f"Agent {self.name} returned non-object output: {type(output).__name__}"
            )

        missing_required = [
            key
            for key in self.required_keys
            if key not in output or output.get(key) in (None, "", [])
        ]
        if missing_required:
            raise RuntimeError(
                f"Agent {self.name} missing required fields: {', '.join(missing_required)}"
            )

        return AgentResult(
            name=self.name,
            output=output,
            raw_text="",
        )


class AgentOrchestrator:
    """顺序多 Agent 流程：solver -> tagger。"""

    def __init__(
        self,
        solver: LLMAgent,
        tagger: LLMAgent,
        is_enabled: Callable[[str], bool] | None = None,
        thinking_resolver: Callable[[str], bool] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self.solver = solver
        self.tagger = tagger
        self.is_enabled = is_enabled
        self.thinking_resolver = thinking_resolver
        self.is_cancelled = is_cancelled

    def solve_and_tag(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        is_cancelled: Callable[[], bool] | None = None,
        on_progress: Callable[[str, str | None], None] | None = None,
    ) -> tuple[list[SolutionBlock], list[TaggingResult]]:
        solutions: list[SolutionBlock] = []
        tags: list[TaggingResult] = []
        cancel_checker = is_cancelled or self.is_cancelled

        problems_list = list(problems)
        total = len(problems_list)

        for i, problem in enumerate(problems_list, 1):
            # 检查任务是否被取消
            if cancel_checker and cancel_checker():
                # 延迟导入避免循环依赖
                from ..services.tasks_service import _TaskCancelled

                raise _TaskCancelled("Task was cancelled by user")

            context = self._build_context(payload, problem)

            def _set_thinking(agent_key: str) -> None:
                if self.thinking_resolver is None:
                    context["agent_thinking"] = True
                    return
                try:
                    context["agent_thinking"] = bool(self.thinking_resolver(agent_key))
                except Exception:
                    context["agent_thinking"] = True

            if on_progress:
                on_progress("solving", f"正在解题 ({i}/{total})...")

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

            if on_progress:
                on_progress("tagging", f"正在标注 ({i}/{total})...")

            _set_thinking("TAGGER")
            tag_payload = self.tagger.run(context).output
            tags.append(self._to_tagging(problem.problem_id, tag_payload))
        return solutions, tags

    @staticmethod
    def _build_context(
        payload: TaskCreateRequest, problem: ProblemBlock
    ) -> dict[str, Any]:
        skills: list[str] = []
        if _needs_chemfig_skill(problem):
            skills.append("chemfig")
        knowledge_candidates = _pick_tag_candidates(
            TagDimension.KNOWLEDGE,
            subject=payload.subject,
            limit=200,
        )
        if not knowledge_candidates:
            knowledge_candidates = [
                str(tag).strip()
                for tag in (payload.knowledge_tags or [])
                if str(tag).strip()
            ]
        error_candidates = _pick_tag_candidates(TagDimension.ERROR, limit=200)
        meta_candidates = _pick_tag_candidates(TagDimension.META, limit=200)

        def _render_candidates(items: list[Any]) -> str:
            if not items:
                return ""
            return "\n".join(
                f"- {item if isinstance(item, str) else getattr(item, 'value', str(item))}"
                for item in items
            )

        return {
            "subject": payload.subject,
            "grade": payload.grade or "",
            "notes": payload.notes or "",
            "problem_text": problem.problem_text,
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
            knowledge_points=utils._coerce_list(
                data.get("knowledge_points"), default=["未标注"]
            ),
            question_type=str(data.get("question_type", "解答题")),
            skills=utils._coerce_list(data.get("skills"), default=["分析推理"]),
            error_hypothesis=utils._coerce_list(
                data.get("error_hypothesis"), default=["待复盘"]
            ),
            recommended_actions=utils._coerce_list(
                data.get("recommended_actions"), default=["完成 2 道同类题"]
            ),
        )


def _load_skill(agent_name: str, name: str) -> str:
    cache_key = f"{agent_name.lower()}::{name}"
    if cache_key in _SKILL_CACHE:
        return _SKILL_CACHE[cache_key]
    path = _SKILL_DIR / agent_name.lower() / f"{name}.md"
    if not path.exists():
        _SKILL_CACHE[cache_key] = ""
        return ""
    text = path.read_text(encoding="utf-8").strip()
    _SKILL_CACHE[cache_key] = text
    return text


def _needs_chemfig_skill(problem: ProblemBlock) -> bool:
    if _CHEMFIG_RE.search(problem.problem_text or ""):
        return True
    if _CHEM_HINT_RE.search(problem.problem_text or ""):
        return True
    for opt in problem.options or []:
        text = getattr(opt, "text", "") or ""
        if _CHEMFIG_RE.search(text) or _CHEM_HINT_RE.search(text):
            return True
    return False


# 说明：类型规整辅助函数已迁移至 utils.py
# - _coerce_list
# - _coerce_int
