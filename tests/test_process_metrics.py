from __future__ import annotations

import os

from oopsnote.ai.process_metrics import process_working_set_bytes


def test_process_memory_sampling_distinguishes_observed_from_unavailable():
    observed = process_working_set_bytes(os.getpid())

    assert observed is not None
    assert observed > 0
    assert process_working_set_bytes(-1) is None
    assert process_working_set_bytes(2_147_483_647) is None
