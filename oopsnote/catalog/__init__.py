"""Tracked catalog assets and import helpers."""

from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data"
KNOWLEDGE_TAGS_PATH = DATA_DIR / "knowledge_tags.json"
KNOWLEDGE_TREES_PATH = DATA_DIR / "knowledge_trees.json"
CHAPTER_TREES_PATH = DATA_DIR / "chapter_trees.json"


__all__ = [
    "CHAPTER_TREES_PATH",
    "DATA_DIR",
    "KNOWLEDGE_TAGS_PATH",
    "KNOWLEDGE_TREES_PATH",
]
