"""pytest configuration: ensure repo root is on sys.path and reset audit between tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _reset_audit() -> None:
    """The audit recorder uses a module-level list in prototype; clear it per test."""
    from kartavya.audit import recorder

    recorder.clear_events()
    yield
    recorder.clear_events()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live_ollama: integration test that requires a local Ollama server"
    )
