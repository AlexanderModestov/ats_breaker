"""Pytest configuration."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env before running tests
load_dotenv()

# Inputs for the caps benchmarks (local, gitignored), env-overridable.
RESUME_PATH = Path(os.getenv("CAPS_RESUME", "output/Alexander Modestov.pdf"))
POSITIONS_PATH = Path(os.getenv("CAPS_POSITIONS", "positions.txt"))


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


@pytest.fixture(autouse=True)
def _dummy_llm_keys(request, monkeypatch):
    """Agent construction needs provider keys; unit tests never make real calls.

    Benchmark tests (real LLM calls) are left untouched so a missing real key
    makes them skip instead of failing with 401s.
    """
    if "benchmark" in request.keywords:
        return
    for var in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if not os.getenv(var):
            monkeypatch.setenv(var, "test-key")
