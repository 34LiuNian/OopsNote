"""Import and normalize XKW tree responses captured in HAR files.

The HAR container is parsed first. Tree JSON lives in
``log.entries[].response.content.text`` and may be plain text or base64.
Unrelated requests in a browser archive are ignored.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

TREE_URL_RE = re.compile(r"/tree/(?P<kind>lk|c)_(?P<bank_id>\d+)(?:_(?P<edition_id>\d+))?\.json$")
SUBJECT_BY_BANK_ID = {
    11: "math",
    13: "physics",
    14: "chemistry",
    15: "biology",
}
SUBJECT_LABELS = {
    "math": "数学",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
}
GENERIC_TITLES = {"其他", "小结"}


class HarTreeError(ValueError):
    """Raised when an archive does not contain one usable XKW tree."""


def normalize_title(value: str) -> str:
    """Normalize Unicode and whitespace without changing subject terminology."""

    value = unicodedata.normalize("NFKC", str(value)).replace("\u3000", " ")
    return re.sub(r"\s+", " ", value).strip()


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", normalize_title(value)).casefold()


def clean_chapter_title(value: str) -> str:
    """Remove edition display numbering while retaining the original on the node."""

    value = normalize_title(value)
    value = re.sub(r"^第\s*[零〇一二三四五六七八九十百\d]+\s*章\s*", "", value)
    value = re.sub(r"^\d+(?:\.\d+)+\.?\s*", "", value)
    value = re.sub(r"^\d+[.、]\s*", "", value)
    return value.strip()


def _decode_content(content: dict[str, Any]) -> str:
    text = content.get("text")
    if not isinstance(text, str) or not text:
        return ""
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text).decode("utf-8-sig")
        except (ValueError, UnicodeDecodeError) as error:
            raise HarTreeError("invalid base64 response content") from error
    return text


def read_xkw_tree(path: Path) -> dict[str, Any]:
    """Extract the single XKW tree response from a HAR archive."""

    try:
        archive = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise HarTreeError(f"cannot read HAR: {path}") from error

    matches: list[dict[str, Any]] = []
    entries = archive.get("log", {}).get("entries", [])
    for entry in entries if isinstance(entries, list) else []:
        url = entry.get("request", {}).get("url", "")
        match = TREE_URL_RE.search(urlsplit(url).path)
        if not match:
            continue
        text = _decode_content(entry.get("response", {}).get("content", {}))
        if not text:
            continue
        try:
            root = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(root, dict) or not isinstance(root.get("children"), list):
            continue
        bank_id = int(match.group("bank_id"))
        if bank_id not in SUBJECT_BY_BANK_ID:
            raise HarTreeError(f"unsupported XKW bank id: {bank_id}")
        matches.append(
            {
                "kind": "knowledge" if match.group("kind") == "lk" else "chapter",
                "bank_id": bank_id,
                "edition_id": (
                    int(match.group("edition_id")) if match.group("edition_id") else None
                ),
                "subject": SUBJECT_BY_BANK_ID[bank_id],
                "request_url": url,
                "captured_at": entry.get("startedDateTime"),
                "payload_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "root": root,
            }
        )
    if len(matches) != 1:
        raise HarTreeError(f"expected one XKW tree in {path}, found {len(matches)}")
    return matches[0]


def _scope_for_path(path: list[str]) -> str:
    joined = "/".join(path)
    if "竞赛" in joined:
        return "competition"
    if "初中衔接" in joined:
        return "prerequisite"
    return "core"


def _clean_node(
    raw: dict[str, Any],
    *,
    bank_id: int,
    kind: str,
    depth: int,
    path: list[str],
    parent_id: str | None,
) -> dict[str, Any]:
    original_title = normalize_title(raw.get("title", ""))
    title = clean_chapter_title(original_title) if kind == "chapter" else original_title
    if not title:
        raise HarTreeError(f"empty title in bank {bank_id}, node {raw.get('id')}")
    source_id = str(raw.get("id", ""))
    if not source_id:
        raise HarTreeError(f"missing node id in bank {bank_id}: {title}")
    node_id = f"xkw:{bank_id}:{source_id}"
    current_path = [*path, title]
    children = [
        _clean_node(
            child,
            bank_id=bank_id,
            kind=kind,
            depth=depth + 1,
            path=current_path,
            parent_id=node_id,
        )
        for child in raw.get("children", [])
    ]
    node: dict[str, Any] = {
        "id": node_id,
        "source_id": source_id,
        "parent_id": parent_id,
        "title": title,
        "depth": depth,
        "scope": _scope_for_path(current_path),
        "selectable": depth >= 2 and title not in GENERIC_TITLES,
        "is_leaf": not children,
        "children": children,
    }
    if original_title != title:
        node["original_title"] = original_title
    if parent_id and normalize_key(path[-1]) == normalize_key(title):
        node["redundant_with_parent"] = True
    return node


def clean_tree(extracted: dict[str, Any]) -> dict[str, Any]:
    root = _clean_node(
        extracted["root"],
        bank_id=extracted["bank_id"],
        kind=extracted["kind"],
        depth=0,
        path=[],
        parent_id=None,
    )
    return {
        "subject": extracted["subject"],
        "subject_label": SUBJECT_LABELS[extracted["subject"]],
        "bank_id": extracted["bank_id"],
        "edition_id": extracted["edition_id"],
        "request_url": extracted["request_url"],
        "captured_at": extracted["captured_at"],
        "payload_sha256": extracted["payload_sha256"],
        "root": root,
    }


def _walk(node: dict[str, Any], path: tuple[str, ...] = ()):
    current = (*path, node["title"])
    yield node, current
    for child in node["children"]:
        yield from _walk(child, current)


def build_knowledge_tags(trees: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a flat search index while preserving all paths for duplicate titles."""

    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], tuple[str, ...]]]] = defaultdict(list)
    for tree in trees:
        subject = tree["subject"]
        for node, path in _walk(tree["root"]):
            if node["selectable"]:
                grouped[(subject, normalize_key(node["title"]))].append((node, path[1:]))

    items: list[dict[str, Any]] = []
    scope_order = {"core": 0, "prerequisite": 1, "competition": 2}
    for (subject, key), occurrences in sorted(grouped.items()):
        occurrences.sort(
            key=lambda item: (
                scope_order[item[0]["scope"]],
                item[0]["depth"],
                "/".join(item[1]),
            )
        )
        primary, primary_path = occurrences[0]
        paths = [list(path) for _, path in occurrences]
        path_aliases = list(dict.fromkeys("/".join(path) for path in paths))
        scopes = list(dict.fromkeys(node["scope"] for node, _ in occurrences))
        item_id = uuid5(NAMESPACE_URL, f"oopsnote:xkw:{subject}:{key}").hex
        items.append(
            {
                "id": item_id,
                "dimension": "knowledge",
                "value": primary["title"],
                "aliases": path_aliases,
                "subject": subject,
                "chapter": primary_path[0] if primary_path else None,
                "ref_count": 0,
                "source": "builtin",
                "source_id": primary["source_id"],
                "source_ids": [node["source_id"] for node, _ in occurrences],
                "parent_id": primary["parent_id"],
                "path": list(primary_path),
                "depth": primary["depth"],
                "scope": primary["scope"],
                "scopes": scopes,
                "is_leaf": all(node["is_leaf"] for node, _ in occurrences),
            }
        )
    items.sort(key=lambda item: (item["subject"], item["value"].casefold(), item["id"]))
    return items


def build_catalogs(paths: Iterable[Path]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    extracted = [read_xkw_tree(Path(path)) for path in paths]
    seen = set()
    knowledge: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    for item in extracted:
        identity = (item["kind"], item["bank_id"])
        if identity in seen:
            raise HarTreeError(f"duplicate {item['kind']} tree for bank {item['bank_id']}")
        seen.add(identity)
        target = knowledge if item["kind"] == "knowledge" else chapters
        target.append(clean_tree(item))
    knowledge.sort(key=lambda item: item["bank_id"])
    chapters.sort(key=lambda item: item["bank_id"])
    knowledge_document = {
        "schema_version": "xkw-knowledge-tree-v1",
        "subjects": {item["subject"]: item for item in knowledge},
    }
    chapter_document = {
        "schema_version": "xkw-chapter-tree-v1",
        "status": "reserve",
        "subjects": {item["subject"]: item for item in chapters},
    }
    tag_document = {
        "schema_version": "oopsnote-tag-index-v2",
        "source": "xkw-knowledge-tree-v1",
        "items": build_knowledge_tags(knowledge),
    }
    return knowledge_document, chapter_document, tag_document


def write_catalogs(paths: Iterable[Path], output_dir: Path) -> dict[str, int]:
    knowledge, chapters, tags = build_catalogs(paths)
    output_dir.mkdir(parents=True, exist_ok=True)
    documents = {
        "knowledge_trees.json": knowledge,
        "chapter_trees.json": chapters,
        "knowledge_tags.json": tags,
    }
    for filename, document in documents.items():
        target = output_dir / filename
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    return {
        "knowledge_subjects": len(knowledge["subjects"]),
        "chapter_subjects": len(chapters["subjects"]),
        "tags": len(tags["items"]),
    }


__all__ = [
    "HarTreeError",
    "build_catalogs",
    "build_knowledge_tags",
    "clean_chapter_title",
    "clean_tree",
    "normalize_key",
    "normalize_title",
    "read_xkw_tree",
    "write_catalogs",
]
