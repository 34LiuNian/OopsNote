"""Canonical case manifest shared by the Pi math smoke and benchmark scripts."""

from __future__ import annotations

from dataclasses import dataclass

from oopsnote.content import normalize_oopsmark


@dataclass(frozen=True, slots=True)
class MathBenchmarkCase:
    name: str
    asset_glob: str
    expected_answer: str


def benchmark_answer_key(value: str) -> str:
    """Ignore only an optional outer inline-math wrapper in scalar answers."""
    normalized = normalize_oopsmark(value)
    if (
        normalized.startswith("$")
        and normalized.endswith("$")
        and not normalized.startswith("$$")
        and not normalized.endswith("$$")
        and normalized.count("$") == 2
    ):
        return normalized[1:-1].strip()
    return normalized


def benchmark_answers_match(actual: str, expected: str) -> bool:
    return benchmark_answer_key(actual) == benchmark_answer_key(expected)


MATH_BENCHMARK_CASES = (
    MathBenchmarkCase("example-1.1", "*page-6-1.png", "C"),
    MathBenchmarkCase("example-1.2", "*page-6-2.png", "42"),
    MathBenchmarkCase("variant-1.2.1", "*page-7-1.png", "0"),
    MathBenchmarkCase("variant-1.2.2", "*page-7-2.png", "0"),
    MathBenchmarkCase("example-1.4", "*page-8-1.png", "C"),
    MathBenchmarkCase("variant-1.4.2", "*region-1.png", "C"),
    MathBenchmarkCase("example-1.5", "*region-2.png", "C"),
    MathBenchmarkCase("variant-1.5.2", "*page-10-1.png", "D"),
)


__all__ = [
    "MATH_BENCHMARK_CASES",
    "MathBenchmarkCase",
    "benchmark_answer_key",
    "benchmark_answers_match",
]
