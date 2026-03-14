from app.default_tags_seed import build_default_tag_payload, load_builtin_tags
from app.tags import TagDimension, TagStore


def test_builtin_tag_seed_contains_expected_dimensions() -> None:
    items = load_builtin_tags()
    dimensions = {item.dimension for item in items}

    assert "knowledge" in dimensions
    assert "error" in dimensions
    assert "meta" in dimensions
    assert len(items) > 1000


def test_knowledge_aliases_preserve_source_paths() -> None:
    items = load_builtin_tags()
    mapping = {item.value: item for item in items if item.dimension == "knowledge"}

    assert "函数" in mapping
    assert any(alias.startswith("数学/") for alias in mapping["函数"].aliases)


def test_payload_shape_matches_tag_store_format() -> None:
    payload = build_default_tag_payload()

    assert isinstance(payload.get("items"), list)
    assert payload["items"]
    first = payload["items"][0]
    assert {"id", "dimension", "value", "aliases", "created_at", "ref_count"}.issubset(first)


def test_tag_store_bootstraps_builtin_tags(tmp_path) -> None:
    store = TagStore(
        tags_path=tmp_path / "tags.json",
        dims_path=tmp_path / "tag_dimensions.json",
    )

    items = store.list(TagDimension.KNOWLEDGE, limit=5000)

    assert items
    assert any(item.value == "函数" for item in items)
