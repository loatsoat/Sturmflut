import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sensoren'))

from verification_plan import VerificationHarness


def test_safety_with_concurrent_requests():
    """Functional – 4.5.1: Safety and Liveness under concurrent access."""
    h = VerificationHarness()
    r = h.run_safety_liveness()
    assert r['safety_ok'],                   f"Safety violated: {r['errors']}"
    assert r['liveness_ok'],                 f"Liveness failed: {r['errors']}"
    assert r['max_concurrent_holders'] <= 1


def test_non_fifo_correctness():
    """Non-functional – 4.5.2: Non-FIFO delivery"""
    h = VerificationHarness()
    r = h.run_non_fifo_mode()
    assert r['safety_ok'],   f"Safety violated under non-FIFO: {r['errors']}"
    assert r['liveness_ok'], f"Liveness failed under non-FIFO: {r['errors']}"


def test_latency_smoke():
    """Non-functional – 4.5.3: Latency smoke test"""
    h = VerificationHarness()
    r = h.run_latency_smoke()
    assert r['timeouts'] == 0, f"{r['timeouts']} timeout(s) in {r['runs']} runs"
    assert r['p50_ms'] < 50,   f"p50 = {r['p50_ms']} ms – exceeds 50 ms threshold"
    assert r['p95_ms'] < 100,  f"p95 = {r['p95_ms']} ms – exceeds 100 ms threshold"
