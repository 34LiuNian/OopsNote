"""Bundled default tag seed builders.

This module turns the two checked-in raw sources under `_tmp/` into the flat
TagStore representation used by the current backend.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .config.subjects import SUBJECTS

_DEFAULT_CREATED_AT = datetime(2026, 3, 9, tzinfo=timezone.utc)
_BUNDLED_JSON_PATH = Path(__file__).with_name("default_tags_builtin.json")
_SUPPORTED_SUBJECTS = ("math", "physics", "chemistry", "english", "biology")
_SUBJECT_ORDER = {key: index for index, key in enumerate(_SUPPORTED_SUBJECTS)}
_SKIP_EXACT_LABELS = {"其他", "其它"}
_TS_CURRICULUM_EXPORTS = {
    "math": "MATH_CURRICULUM",
    "physics": "PHYSICS_CURRICULUM",
    "chemistry": "CHEMISTRY_CURRICULUM",
    "english": "ENGLISH_CURRICULUM",
    "biology": "BIOLOGY_CURRICULUM",
}
_DEFAULT_ERROR_TAGS = {
    "审题不清": ["读题失误", "忽略关键词"],
    "概念混淆": ["概念不清", "知识点混淆"],
    "公式记忆不牢": ["公式不熟", "定理记忆不牢"],
    "计算错误": ["算错", "运算失误"],
    "符号错误": ["正负号错误", "符号看错"],
    "步骤遗漏": ["推导不完整", "漏步骤"],
    "分类讨论遗漏": ["情况遗漏", "分类不全"],
    "图像理解偏差": ["图形理解偏差", "图像分析失误"],
    "条件使用错误": ["条件漏用", "隐含条件未使用"],
    "单位与规范失误": ["单位遗漏", "书写不规范"],
}
_DEFAULT_META_TAGS = {
    "教材": ["课本"],
    "作业": ["课后作业"],
    "练习册": ["教辅", "习题册"],
    "单元测试": ["单元卷"],
    "月考": [],
    "期中": ["期中考试"],
    "期末": ["期末考试"],
    "模拟题": ["模考", "模拟卷"],
    "真题": ["高考真题", "中考真题"],
    "竞赛": ["竞赛题"],
    "练透": [],
    "必刷题": [],
}


@dataclass(frozen=True)
class BuiltinTagRecord:
    """Flat built-in tag record compatible with TagStore."""

    dimension: str
    value: str
    aliases: tuple[str, ...] = ()
    id: str = ""
    ref_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id or uuid5(NAMESPACE_URL, f"oopsnote:{self.dimension}:{self.value}").hex,
            "dimension": self.dimension,
            "value": self.value,
            "aliases": list(self.aliases),
            "ref_count": self.ref_count,
        }


@dataclass
class _KnowledgeEntry:
    subject_key: str
    leaf: str
    aliases: set[str] = field(default_factory=set)


class _JsLiteralParser:
    """Minimal parser for the checked-in tag-data TS object literals."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0

    def parse(self) -> Any:
        value = self._parse_value()
        self._skip_ignored()
        return value

    def _skip_ignored(self) -> None:
        while self.index < self.length:
            if self.text[self.index].isspace():
                self.index += 1
                continue
            if self.text.startswith("//", self.index):
                newline = self.text.find("\n", self.index)
                self.index = self.length if newline < 0 else newline + 1
                continue
            if self.text.startswith("/*", self.index):
                close = self.text.find("*/", self.index + 2)
                if close < 0:
                    self.index = self.length
                else:
                    self.index = close + 2
                continue
            break

    def _parse_value(self) -> Any:
        self._skip_ignored()
        if self.index >= self.length:
            raise ValueError("Unexpected end of TS literal")
        current = self.text[self.index]
        if current == "{":
            return self._parse_object()
        if current == "[":
            return self._parse_array()
        if current in {"'", '"'}:
            return self._parse_string()
        if current == "-" or current.isdigit():
            return self._parse_number()
        identifier = self._parse_identifier()
        if identifier == "true":
            return True
        if identifier == "false":
            return False
        if identifier == "null":
            return None
        return identifier

    def _parse_object(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        self.index += 1
        while True:
            self._skip_ignored()
            if self.index >= self.length:
                raise ValueError("Unterminated object literal")
            if self.text[self.index] == "}":
                self.index += 1
                return result
            if self.text[self.index] in {"'", '"'}:
                key = self._parse_string()
            else:
                key = self._parse_identifier()
            self._skip_ignored()
            if self.index >= self.length or self.text[self.index] != ":":
                raise ValueError("Expected ':' in object literal")
            self.index += 1
            result[key] = self._parse_value()
            self._skip_ignored()
            if self.index < self.length and self.text[self.index] == ",":
                self.index += 1
                continue
            if self.index < self.length and self.text[self.index] == "}":
                self.index += 1
                return result

    def _parse_array(self) -> list[Any]:
        result: list[Any] = []
        self.index += 1
        while True:
            self._skip_ignored()
            if self.index >= self.length:
                raise ValueError("Unterminated array literal")
            if self.text[self.index] == "]":
                self.index += 1
                return result
            result.append(self._parse_value())
            self._skip_ignored()
            if self.index < self.length and self.text[self.index] == ",":
                self.index += 1
                continue
            if self.index < self.length and self.text[self.index] == "]":
                self.index += 1
                return result

    def _parse_string(self) -> str:
        quote = self.text[self.index]
        self.index += 1
        chunks: list[str] = []
        escapes = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "\\": "\\",
            "'": "'",
            '"': '"',
        }
        while self.index < self.length:
            current = self.text[self.index]
            self.index += 1
            if current == quote:
                return "".join(chunks)
            if current == "\\":
                if self.index >= self.length:
                    break
                escaped = self.text[self.index]
                self.index += 1
                chunks.append(escapes.get(escaped, escaped))
                continue
            chunks.append(current)
        raise ValueError("Unterminated string literal")

    def _parse_number(self) -> int | float:
        start = self.index
        while self.index < self.length and self.text[self.index] in "-+0123456789.eE":
            self.index += 1
        token = self.text[start:self.index]
        return float(token) if any(ch in token for ch in ".eE") else int(token)

    def _parse_identifier(self) -> str:
        start = self.index
        while self.index < self.length and re.match(r"[A-Za-z0-9_$]", self.text[self.index]):
            self.index += 1
        if start == self.index:
            raise ValueError(f"Expected identifier at position {self.index}")
        return self.text[start:self.index]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_label(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^\d+(?:\.\d+)+(?:\s+|$)", "", text).strip()
    text = text.rstrip("*").strip()
    return text


def _extract_assignment_literal(text: str, export_name: str) -> Any:
    pattern = re.compile(
        rf"export\s+const\s+{re.escape(export_name)}(?:\s*:[^=]+)?=",
        re.S,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Export {export_name} not found")
    parser = _JsLiteralParser(text[match.end() :])
    return parser.parse()


def _build_path_aliases(subject_label: str, grade: str | None, *parts: str) -> set[str]:
    normalized_parts = [_normalize_label(p) for p in parts if _normalize_label(p)]
    aliases: set[str] = set()
    if not normalized_parts:
        return aliases
    if grade:
        normalized_grade = _normalize_label(grade)
        aliases.add("/".join([subject_label, normalized_grade, *normalized_parts]))
    aliases.add("/".join([subject_label, *normalized_parts]))
    return aliases


def _iter_filatex_entries() -> list[_KnowledgeEntry]:
    source_path = _repo_root() / "_tmp" / "tag.json"
    if not source_path.exists():
        return []
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    roots = raw.get("data", []) if isinstance(raw, dict) else []
    entries: dict[tuple[str, str], _KnowledgeEntry] = {}

    def walk(node: dict[str, Any], path_parts: list[str]) -> None:
        name = _normalize_label(node.get("name"))
        if not name:
            return
        current_path = [*path_parts, name]
        if name not in _SKIP_EXACT_LABELS:
            key = ("math", name)
            entry = entries.setdefault(key, _KnowledgeEntry(subject_key="math", leaf=name))
            entry.aliases.update(_build_path_aliases(SUBJECTS["math"], None, *current_path))
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                walk(child, current_path)

    for root in roots or []:
        if isinstance(root, dict):
            walk(root, [])
    return list(entries.values())


def _iter_curriculum_entries() -> list[_KnowledgeEntry]:
    source_dir = _repo_root() / "_tmp" / "tag-data"
    if not source_dir.exists():
        return []
    entries: dict[tuple[str, str], _KnowledgeEntry] = {}

    def add_entry(subject_key: str, leaf: str, aliases: set[str]) -> None:
        leaf = _normalize_label(leaf)
        if not leaf or leaf in _SKIP_EXACT_LABELS:
            return
        key = (subject_key, leaf)
        entry = entries.setdefault(key, _KnowledgeEntry(subject_key=subject_key, leaf=leaf))
        entry.aliases.update(aliases)

    for subject_key, export_name in _TS_CURRICULUM_EXPORTS.items():
        path = source_dir / f"{subject_key}.ts"
        if not path.exists():
            continue
        curriculum = _extract_assignment_literal(path.read_text(encoding="utf-8"), export_name)
        if not isinstance(curriculum, dict):
            continue
        subject_label = SUBJECTS[subject_key]
        for grade, chapters in curriculum.items():
            normalized_grade = _normalize_label(grade)
            if not isinstance(chapters, list):
                continue
            for chapter in chapters:
                if not isinstance(chapter, dict):
                    continue
                chapter_name = _normalize_label(chapter.get("chapter"))
                if not chapter_name:
                    continue
                add_entry(
                    subject_key,
                    chapter_name,
                    _build_path_aliases(subject_label, normalized_grade, chapter_name),
                )
                sections = chapter.get("sections")
                if isinstance(sections, list):
                    for section in sections:
                        if not isinstance(section, dict):
                            continue
                        section_name = _normalize_label(section.get("section"))
                        if not section_name:
                            continue
                        add_entry(
                            subject_key,
                            section_name,
                            _build_path_aliases(subject_label, normalized_grade, chapter_name, section_name),
                        )
                        for tag in section.get("tags", []) or []:
                            tag_name = _normalize_label(tag)
                            if not tag_name:
                                continue
                            add_entry(
                                subject_key,
                                tag_name,
                                _build_path_aliases(
                                    subject_label,
                                    normalized_grade,
                                    chapter_name,
                                    section_name,
                                    tag_name,
                                ),
                            )
                    continue
                for tag in chapter.get("tags", []) or []:
                    tag_name = _normalize_label(tag)
                    if not tag_name:
                        continue
                    add_entry(
                        subject_key,
                        tag_name,
                        _build_path_aliases(subject_label, normalized_grade, chapter_name, tag_name),
                    )
    return list(entries.values())


def _build_knowledge_records() -> list[BuiltinTagRecord]:
    grouped: dict[tuple[str, str], _KnowledgeEntry] = {}
    for entry in [*_iter_filatex_entries(), *_iter_curriculum_entries()]:
        key = (entry.subject_key, entry.leaf)
        current = grouped.setdefault(key, _KnowledgeEntry(subject_key=entry.subject_key, leaf=entry.leaf))
        current.aliases.update(entry.aliases)

    subjects_by_leaf: dict[str, set[str]] = {}
    for subject_key, leaf in grouped:
        subjects_by_leaf.setdefault(leaf, set()).add(subject_key)

    records: list[tuple[int, str, BuiltinTagRecord]] = []
    for (subject_key, leaf), entry in grouped.items():
        subject_label = SUBJECTS[subject_key]
        needs_subject_prefix = len(subjects_by_leaf.get(leaf, set())) > 1
        value = f"{subject_label}/{leaf}" if needs_subject_prefix else leaf
        aliases = {alias for alias in entry.aliases if alias and alias != value}
        if needs_subject_prefix:
            aliases.add(leaf)
        record = BuiltinTagRecord(
            dimension="knowledge",
            value=value,
            aliases=tuple(sorted(aliases)),
        )
        records.append((_SUBJECT_ORDER.get(subject_key, 999), value, record))

    records.sort(key=lambda item: (item[0], item[1]))
    return [record for _, _, record in records]


def _build_simple_dimension_records(
    dimension: str,
    values: dict[str, list[str]],
) -> list[BuiltinTagRecord]:
    return [
        BuiltinTagRecord(
            dimension=dimension,
            value=_normalize_label(value),
            aliases=tuple(sorted({_normalize_label(alias) for alias in aliases if _normalize_label(alias)})),
        )
        for value, aliases in sorted(values.items())
        if _normalize_label(value)
    ]


@lru_cache(maxsize=1)
def build_default_tag_payload_from_sources() -> dict[str, Any]:
    """Build the bundled payload from the temporary raw source files."""

    records = [
        *_build_knowledge_records(),
        *_build_simple_dimension_records("error", _DEFAULT_ERROR_TAGS),
        *_build_simple_dimension_records("meta", _DEFAULT_META_TAGS),
    ]
    return {"items": [record.as_dict() for record in records]}


@lru_cache(maxsize=1)
def load_builtin_tags() -> tuple[BuiltinTagRecord, ...]:
    """Return bundled default tags from the checked-in permanent snapshot."""

    if not _BUNDLED_JSON_PATH.exists():
        payload = build_default_tag_payload_from_sources()
    else:
        payload = json.loads(_BUNDLED_JSON_PATH.read_text(encoding="utf-8"))

    items = payload.get("items", []) if isinstance(payload, dict) else []
    return tuple(BuiltinTagRecord(**item) for item in items)


def build_default_tag_payload() -> dict[str, Any]:
    """Serialize bundled defaults to the on-disk TagStore payload shape."""

    return {"items": [record.as_dict() for record in load_builtin_tags()]}
