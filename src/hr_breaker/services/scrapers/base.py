import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from bs4 import BeautifulSoup

from hr_breaker.config import get_settings
from hr_breaker.models import JobHints


@dataclass
class ScrapedJob:
    """Result of scraping: cleaned body text plus structured hints (may be empty)."""

    text: str
    hints: JobHints | None = None


def _clean(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _iter_jsonld(data):
    """Yield candidate dict nodes from a parsed JSON-LD payload.

    Flattens top-level lists and @graph containers.
    """
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld(item)
    elif isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_jsonld(item)


def _types_contains(node: dict, wanted: str) -> bool:
    t = node.get("@type")
    if isinstance(t, str):
        return t == wanted
    if isinstance(t, list):
        return wanted in t
    return False


def _org_name(org) -> str | None:
    if isinstance(org, str):
        return _clean(org)
    if isinstance(org, dict):
        return _clean(org.get("name"))
    if isinstance(org, list):
        for item in org:
            name = _org_name(item)
            if name:
                return name
    return None


def _remote_label(job_location_type) -> str | None:
    if isinstance(job_location_type, str) and job_location_type.upper() == "TELECOMMUTE":
        return "Remote"
    return None


def _format_location(job_location) -> str | None:
    """Collapse a schema.org jobLocation into 'City, Region, Country' (best-effort)."""
    if job_location is None:
        return None
    if isinstance(job_location, list):
        for item in job_location:
            loc = _format_location(item)
            if loc:
                return loc
        return None
    if isinstance(job_location, str):
        return _clean(job_location)
    if not isinstance(job_location, dict):
        return None
    address = job_location.get("address", job_location)
    if isinstance(address, str):
        return _clean(address)
    if not isinstance(address, dict):
        return None
    parts = [
        _clean(address.get("addressLocality")),
        _clean(address.get("addressRegion")),
        _clean(address.get("addressCountry")),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) or None


class ScrapingError(Exception):
    """Raised when job scraping fails."""

    pass


class CloudflareBlockedError(ScrapingError):
    """Raised when blocked by Cloudflare or similar bot protection."""

    pass


class BaseScraper(ABC):
    """Base class for job posting scrapers."""

    name: str

    @abstractmethod
    def scrape(self, url: str) -> str:
        """Return job text or raise ScrapingError."""
        pass

    def is_cloudflare_blocked(self, html: str) -> bool:
        """Check if response is a Cloudflare challenge page."""
        indicators = [
            "Just a moment...",
            "cf-browser-verification",
            "challenge-platform",
            "_cf_chl_opt",
            "Checking your browser",
        ]
        return any(ind in html for ind in indicators)

    def extract_job_text(self, html: str) -> str:
        """Extract job posting text from HTML."""
        settings = get_settings()
        soup = BeautifulSoup(html, "html.parser")

        # Remove non-content chrome (header kept: often holds company/location)
        for element in soup(["script", "style", "nav", "footer"]):
            element.decompose()

        # Try common job posting containers
        containers = [
            soup.find("div", class_=lambda x: x and "job" in x.lower()),
            soup.find("article"),
            soup.find("main"),
            soup.find("div", id=lambda x: x and "job" in x.lower()),
        ]

        for container in containers:
            if container:
                text = container.get_text(separator="\n", strip=True)
                if len(text) > settings.scraper_min_text_length:
                    return text

        # Fallback: get body text
        return soup.get_text(separator="\n", strip=True)

    def extract_hints(self, html: str) -> JobHints:
        """Harvest structured title/company/location from raw HTML.

        Priority: schema.org JobPosting JSON-LD, then OpenGraph/<title> meta.
        Records per-field provenance (company_source / title_source) so the
        parser can rank meta-sourced values below the URL slug / grounded LLM.
        Never invents — None when nothing is found. Must run on the original
        HTML, before extract_job_text strips <script>.
        """
        soup = BeautifulSoup(html, "html.parser")
        title = company = location = None
        company_source = title_source = None

        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text() or ""
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            for node in _iter_jsonld(data):
                if not _types_contains(node, "JobPosting"):
                    continue
                if not title:
                    title = _clean(node.get("title"))
                    if title:
                        title_source = "json-ld"
                if not company:
                    company = _org_name(node.get("hiringOrganization"))
                    if company:
                        company_source = "json-ld"
                if not location:
                    location = _format_location(node.get("jobLocation")) or _remote_label(
                        node.get("jobLocationType")
                    )

        if not company:
            og_site = soup.find("meta", property="og:site_name")
            if og_site and og_site.get("content"):
                company = _clean(og_site["content"])
                if company:
                    company_source = "meta"
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = _clean(og_title["content"])
            elif soup.title and soup.title.string:
                title = _clean(soup.title.string)
            if title:
                title_source = "meta"

        return JobHints(
            title=title,
            company=company,
            location=location,
            company_source=company_source,
            title_source=title_source,
        )

    def _build_result(self, html: str) -> ScrapedJob:
        """Bundle cleaned text + structured hints from one HTML document."""
        return ScrapedJob(text=self.extract_job_text(html), hints=self.extract_hints(html))
