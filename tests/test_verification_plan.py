import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sensoren'))

from verification_plan import run_verification_plan


def test_verification_plan_reports_expected_outcomes():
    result = run_verification_plan()
    safety = result['safety_liveness']
    failure = result['failure_mode']

    assert safety['safety_ok'] is True
    assert safety['liveness_ok'] is True
    assert safety['max_concurrent_holders'] <= 1
    assert failure['failure_ok'] is True
    assert failure['final_state'] == 'IDLE'
