import os
import sys
from datetime import datetime, timezone

# Ensure auth settings exist before importing routers.users
os.environ.setdefault("JWT_SECRET", "test-secret")

# Ensure backend root is importable when running tests from /backend/tests
root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root not in sys.path:
    sys.path.insert(0, root)

from routers.users import _to_utc_naive


def test_to_utc_naive_keeps_naive_values():
    dt = datetime(2026, 4, 1, 7, 30, 0)
    normalized = _to_utc_naive(dt)
    assert normalized == dt
    assert normalized.tzinfo is None


def test_to_utc_naive_converts_aware_values_to_utc_naive():
    aware = datetime(2026, 4, 1, 7, 30, 0, tzinfo=timezone.utc)
    normalized = _to_utc_naive(aware)
    assert normalized == datetime(2026, 4, 1, 7, 30, 0)
    assert normalized.tzinfo is None


def test_to_utc_naive_handles_none():
    assert _to_utc_naive(None) is None
