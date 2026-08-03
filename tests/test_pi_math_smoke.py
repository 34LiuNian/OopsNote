from __future__ import annotations

import pytest

from scripts.benchmarks import pi_math_benchmark, pi_math_smoke
from scripts.benchmarks.pi_math_cases import MATH_BENCHMARK_CASES


def test_math_smoke_and_benchmark_share_the_canonical_case_manifest():
    assert pi_math_smoke.SMOKE_CASE is MATH_BENCHMARK_CASES[0]
    assert pi_math_benchmark.MATH_BENCHMARK_CASES is MATH_BENCHMARK_CASES
    assert pi_math_smoke.SMOKE_CASE.name == "example-1.1"
    assert pi_math_smoke.SMOKE_CASE.asset_glob == "*page-6-1.png"
    assert pi_math_smoke.SMOKE_CASE.expected_answer == "C"


@pytest.mark.parametrize(
    ("actual", "expected", "matches"),
    [
        ("0", "0", True),
        ("$0$", "0", True),
        ("$x=1$", "x=1", True),
        ("$$0$$", "0", False),
        ("$1+1$", "2", False),
        (r"$\frac{1}{2}$", "0.5", False),
    ],
)
def test_benchmark_answer_comparison_only_ignores_inline_math_wrapper(
    actual,
    expected,
    matches,
):
    assert pi_math_smoke.benchmark_answers_match(actual, expected) is matches
