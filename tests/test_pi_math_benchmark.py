from __future__ import annotations

from scripts.benchmarks import pi_math_benchmark as benchmark


def test_benchmark_table_renders_stage_and_cost_metrics():
    table = benchmark.markdown_table([{
        "case": "example-1.1",
        "expected": "C",
        "answer": "C",
        "status": "completed",
        "duration_ms": 1234,
        "stages": {"ocr": 100, "solving": 200, "verifying": 300, "tagging": 400},
        "input_tokens": 10,
        "output_tokens": 20,
        "cache_tokens": 30,
        "cost": 0.001,
    }])

    assert "example-1.1" in table
    assert "1.23s" in table
    assert "10/20/30" in table


def test_benchmark_summary_uses_nearest_rank_p95():
    rows = [
        {
            "status": "completed",
            "answer": "C",
            "expected": "C",
            "duration_ms": duration,
            "stages": {},
            "input_tokens": 1,
            "output_tokens": 2,
            "cache_tokens": 3,
            "cost": 0.001,
        }
        for duration in (1000, 2000, 3000, 4000)
    ]

    summary = benchmark.summary_table(rows)

    assert "completed / total | 4/4" in summary
    assert "P95 duration (nearest rank) | 4.00s" in summary
    assert "4 / 8 / 12" in summary
