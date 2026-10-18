import os
import tempfile

# Tests get their own throwaway database, never data/inko.db.
os.environ["INKO_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="inko-test-"), "test.db")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def backend(monkeypatch):
    """Every test talks to a fake analysis backend (shared/fixtures responses), never the network.
    Returns the list of JPEGs it was sent."""
    from .helpers import fake_backend
    return fake_backend(monkeypatch)
