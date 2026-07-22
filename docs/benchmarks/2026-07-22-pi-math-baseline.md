# Pi math baseline - 2026-07-22

Dataset: eight existing image crops from the curated function-question vault
Provider/model: DeepSeek / `deepseek-v4-flash`
OCR: configured DashScope vision model
Pipeline: OCR -> solve -> verify -> tag -> finalize

| Case | Expected | Result | OCR | Solve | Verify | Tag | Total |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| example-1.1 | C | C | 11.38s | 1.75s | 3.85s | 8.04s | 62.16s |
| example-1.2 | 42 | 42 | 12.37s | 5.20s | 7.19s | 9.67s | 71.08s |
| variant-1.2.1 | 0 | 0 | 11.65s | 5.46s | 5.23s | 8.62s | 69.11s |
| variant-1.2.2 | 0 | 0 | 11.08s | 3.66s | 3.71s | 4.29s | 58.69s |
| example-1.4 | C | C | 14.86s | 7.09s | 6.27s | 12.11s | 72.23s |
| variant-1.4.2 | C | C | 14.37s | 1.86s | 4.80s | 10.85s | 66.70s |
| example-1.5 | C | C | 15.33s | 3.98s | 4.45s | 5.50s | 54.81s |
| variant-1.5.2 | D | D | 8.59s | 5.44s | 2.34s | 4.87s | 50.58s |

## Summary

- Completion and reference-answer match: 8/8.
- Persisted duration: 505.36s total, 63.17s mean, 64.43s P50, 72.23s nearest-rank P95.
- Mean recorded stages: OCR 12.45s, solve 4.30s, verify 4.73s, tag 7.99s.
- Tokens: 60,113 input, 36,477 output, 789,888 cache.
- Pi-reported cost total: 0.020841; the provider/currency interpretation is intentionally not inferred here.
- Command wall duration was 519.6s. The gap between end-to-end and named stages remains an instrumentation target.

This is a migration smoke baseline, not a quality claim. It covers only eight mathematics items and does not replace the planned 60-question multi-subject golden set or manual revision scoring.
