"""多维度搜索引擎。

目前基于 Task JSON 内存过滤。后续可升级为 SQLite/全文索引。
"""

from __future__ import annotations

import re

from .models import Problem, SearchQuery, TaskRecord


class Searcher:
    """Task 级内存搜索引擎。"""

    def __init__(self, tasks: list[TaskRecord]) -> None:
        self._tasks = tasks

    def search(self, query: SearchQuery) -> list[Problem]:
        """按条件筛选题目，返回匹配的 Problem 列表。"""
        results: list[Problem] = []

        for task in self._tasks:
            if task.problem and self._match(task.problem, query):
                results.append(task.problem)

        # 按时间倒序
        results.sort(key=lambda p: p.created_at, reverse=True)
        return results[: max(1, query.limit)]

    @staticmethod
    def _match(p: Problem, q: SearchQuery) -> bool:
        # subject
        if q.subject and p.subject.casefold() != q.subject.casefold():
            return False

        # tags（匹配 knowledge_points + error_hypothesis）
        if q.tags:
            search_tags = {t.casefold() for t in q.tags}
            problem_tags = {t.casefold() for t in p.knowledge_points + p.error_hypothesis}
            if not search_tags.issubset(problem_tags):
                return False

        # error_type
        if q.error_type and q.error_type.casefold() not in {
            e.casefold() for e in p.error_hypothesis
        }:
            return False

        # since
        if q.since:
            # SearchQuery validates the input once at the boundary. Align
            # legacy naive timestamps here without silently accepting invalid
            # query values or leaking a naive/aware comparison error.
            since_dt = q.since
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=p.created_at.tzinfo)
            elif p.created_at.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=None)
            if p.created_at < since_dt:
                return False

        # regex（搜索 problem_text + answer + explanation）
        if q.regex:
            try:
                pat = re.compile(q.regex, re.IGNORECASE)
                text = f"{p.problem_text} {p.answer} {p.explanation}"
                if not pat.search(text):
                    return False
            except re.error:
                return False  # 非法正则 → 不匹配

        return True
