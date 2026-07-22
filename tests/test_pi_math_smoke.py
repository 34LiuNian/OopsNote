from __future__ import annotations

from scripts.benchmarks import pi_math_smoke


def test_math_smoke_case_comes_from_the_curated_vault():
    question, expected_option = pi_math_smoke.source_case()

    assert question.startswith("【例1.1】")
    assert "f(1) + f(2)" in question
    assert expected_option == "C"
