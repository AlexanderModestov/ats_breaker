"""Async polling for optimization status."""

import asyncio
from bot.services.api_client import APIClient


async def poll_until_done(
    client: APIClient, telegram_id: int, run_id: str, timeout: int = 300
) -> dict:
    """Poll optimization status every 4 seconds until done or timeout."""
    elapsed = 0
    while elapsed < timeout:
        status = await client.get_optimization_status(telegram_id, run_id)
        if status["status"] == "completed":
            return status
        if status["status"] == "failed":
            raise RuntimeError(status.get("error", "Optimization failed"))
        await asyncio.sleep(4)
        elapsed += 4
    raise TimeoutError("Optimization timed out")
