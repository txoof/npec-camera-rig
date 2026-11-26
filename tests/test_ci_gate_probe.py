import pytest


@pytest.mark.unit
def test_ci_gate_probe_fails_on_purpose() -> None:
    # Throwaway: proves a failing unit test blocks the merge (#546). Never merged.
    assert False, "deliberate failure to test the required check"
