import asyncio
import logging

from .base import BaseScraper, CloudflareBlockedError, ScrapingError

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None
    PlaywrightTimeout = None


class PlaywrightScraper(BaseScraper):
    """Browser-based scraper using Playwright."""

    name = "playwright"

    def __init__(self, timeout: float = 60000):  # ms for playwright
        self.timeout = timeout

    async def scrape_async(self, url: str) -> str:
        """Scrape job posting using headless browser (async)."""
        if not PLAYWRIGHT_AVAILABLE:
            raise ScrapingError(
                "Playwright not installed. Install with: "
                "uv pip install 'hr-breaker[browser]' && playwright install chromium"
            )

        try:
            async with async_playwright() as p:
                # Launch with stealth settings to avoid detection
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ],
                )
                try:
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36",
                        locale="en-US",
                        timezone_id="America/New_York",
                        viewport={"width": 1920, "height": 1080},
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                            "Accept-Encoding": "gzip, deflate, br",
                            "Connection": "keep-alive",
                            "Upgrade-Insecure-Requests": "1",
                            "Sec-Fetch-Dest": "document",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Site": "none",
                            "Sec-Fetch-User": "?1",
                        },
                    )
                    page = await context.new_page()

                    # Remove webdriver property to avoid detection
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                    """)

                    # Try domcontentloaded first (faster), fallback to load
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                        # Wait a bit for JS to render
                        await page.wait_for_timeout(2000)
                    except PlaywrightTimeout:
                        logger.warning(f"Timeout on domcontentloaded, trying with load event")
                        await page.goto(url, wait_until="load", timeout=self.timeout)

                    html = await page.content()

                    if self.is_cloudflare_blocked(html):
                        raise CloudflareBlockedError(
                            f"Cloudflare blocked even with browser: {url}"
                        )

                    return self.extract_job_text(html)
                finally:
                    await browser.close()
        except PlaywrightTimeout:
            raise ScrapingError(f"Playwright timeout loading {url}")
        except Exception as e:
            if isinstance(e, (ScrapingError, CloudflareBlockedError)):
                raise
            raise ScrapingError(f"Playwright error: {e}")

    def scrape(self, url: str) -> str:
        """Scrape job posting using headless browser (sync wrapper)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in async context - run in thread pool to avoid blocking
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.scrape_async(url))
                return future.result()
        else:
            # No async loop - run directly
            return asyncio.run(self.scrape_async(url))
