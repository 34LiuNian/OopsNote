from __future__ import annotations

import base64
import json
from pathlib import Path

from oopsnote.catalog import KNOWLEDGE_TAGS_PATH, KNOWLEDGE_TREES_PATH
from oopsnote.catalog.xkw import (
    build_catalogs,
    clean_chapter_title,
    read_xkw_tree,
)
from oopsnote.core import TagDimension, TagStore


def _node(node_id: int, title: str, children: list[dict] | None = None) -> dict:
    return {
        "id": node_id,
        "parentId": 0,
        "title": title,
        "children": children or [],
    }


def _har_entry(url: str, payload: dict, *, encoded: bool = False) -> dict:
    text = json.dumps(payload, ensure_ascii=False)
    content = {
        "mimeType": "application/json",
        "text": base64.b64encode(text.encode()).decode() if encoded else text,
    }
    if encoded:
        content["encoding"] = "base64"
    return {
        "startedDateTime": "2026-07-25T00:00:00+08:00",
        "request": {"url": url},
        "response": {"status": 200, "content": content},
    }


def _write_har(path: Path, entries: list[dict]) -> Path:
    path.write_text(
        json.dumps({"log": {"version": "1.2", "entries": entries}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_har_parser_uses_tree_response_and_decodes_base64(tmp_path):
    root = _node(1, "高中数学综合库", [_node(2, "函数")])
    path = _write_har(
        tmp_path / "capture.har",
        [
            _har_entry("https://example.test/unrelated.json", {"ok": True}),
            _har_entry("https://static.zxxk.com/zujuan/tree/lk_11.json?v=1", root, encoded=True),
        ],
    )

    extracted = read_xkw_tree(path)

    assert extracted["kind"] == "knowledge"
    assert extracted["subject"] == "math"
    assert extracted["root"]["children"][0]["title"] == "函数"


def test_catalog_preserves_tree_but_deduplicates_flat_titles(tmp_path):
    knowledge = _node(
        1,
        "高中数学综合库",
        [
            _node(2, "函数", [_node(3, "单调性")]),
            _node(4, "导数", [_node(5, "单调性")]),
        ],
    )
    chapter = _node(10, "人教A版", [_node(11, "第一章 函数", [_node(12, "1.1 函数概念")])])
    knowledge_path = _write_har(
        tmp_path / "knowledge.har",
        [_har_entry("https://static.zxxk.com/zujuan/tree/lk_11.json", knowledge)],
    )
    chapter_path = _write_har(
        tmp_path / "chapter.har",
        [_har_entry("https://static.zxxk.com/zujuan/tree/c_11_100.json", chapter)],
    )

    trees, chapters, tags = build_catalogs([knowledge_path, chapter_path])

    assert len(trees["subjects"]["math"]["root"]["children"]) == 2
    monotonicity = [item for item in tags["items"] if item["value"] == "单调性"]
    assert len(monotonicity) == 1
    assert len(monotonicity[0]["source_ids"]) == 2
    assert chapters["subjects"]["math"]["root"]["children"][0]["title"] == "函数"
    assert clean_chapter_title("1.1  函数概念") == "函数概念"


def test_generated_catalog_is_runtime_source(tmp_path):
    store = TagStore(
        user_path=tmp_path / "tags_user.json",
        builtin_path=KNOWLEDGE_TAGS_PATH,
        tree_path=KNOWLEDGE_TREES_PATH,
    )

    results = store.search(
        TagDimension.KNOWLEDGE,
        "牛顿第二定律",
        subject="physics",
        scope="core",
    )
    assert results
    assert results[0].value == "牛顿第二定律"
    assert {item.subject for item in results} == {"physics"}

    tree = store.knowledge_tree("biology")
    assert set(tree["subjects"]) == {"biology"}
    assert tree["subjects"]["biology"]["root"]["title"] == "高中生物综合库"
