"""Pytest configuration."""

import pytest
from dotenv import load_dotenv

# Load .env before running tests
load_dotenv()


def pytest_collection_modifyitems(config, items):
    """Skip benchmark-marked tests unless `-m benchmark` (or similar) is used."""
    if "benchmark" in (config.getoption("-m") or ""):
        return
    skip_bench = pytest.mark.skip(reason="benchmark test; run with -m benchmark")
    for item in items:
        if "benchmark" in item.keywords:
            item.add_marker(skip_bench)


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
