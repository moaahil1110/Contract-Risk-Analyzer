import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from core.rate_limit import reset_rate_limits

    reset_rate_limits()
    yield
    reset_rate_limits()
