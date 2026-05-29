import io
import sys

import pytest


@pytest.fixture(autouse=True)
def _readable_stdin(monkeypatch):
    """Provide an empty, readable stdin so any unmocked ``input()`` call
    (e.g. an approval prompt defaulting to "No") returns "" instead of
    raising ``OSError`` under pytest's output capture."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n" * 1000))
    yield
