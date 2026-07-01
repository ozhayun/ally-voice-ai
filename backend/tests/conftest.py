import sys
import os
import pytest

# Make the backend root importable without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def clear_sessions_and_logs():
    """Reset in-memory state before each test to prevent cross-test pollution."""
    from services.builder import sessions
    from routers.calls import call_logs
    sessions.clear()
    call_logs.clear()
    yield
    sessions.clear()
    call_logs.clear()
