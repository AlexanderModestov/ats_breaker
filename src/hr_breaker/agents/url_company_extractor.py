"""Extract company slug from known ATS URLs.

Used by job_parser as a strong signal for company name when the LLM
extraction is ungrounded or disagrees with the URL.
"""

from urllib.parse import urlparse

# Tier 1: leftmost subdomain is the company.
# E.g. podcastle.bamboohr.com -> "podcastle"
SUBDOMAIN_HOSTS = {
    "bamboohr.com",
    "workable.com",
    "recruitee.com",
    "teamtailor.com",
    "breezy.hr",
    "myworkdayjobs.com",
}

# Tier 2: first path segment under a known host.
# E.g. boards.greenhouse.io/podcastle/jobs/123 -> "podcastle"
PATH_HOSTS = {
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "apply.workable.com",
}

# Subdomains/path-segments that are common platform routes, not companies.
RESERVED = {"www", "jobs", "careers", "apply", "boards", "hire"}


def extract_company_from_url(url: str) -> str | None:
    """Return company slug from known ATS URLs, or None.

    Tier 2 (path-host) is checked first because some hosts like
    apply.workable.com would otherwise match Tier 1 with the wrong slug.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None

    # Tier 2: explicit path-host match
    if host in PATH_HOSTS:
        segments = [s for s in parsed.path.split("/") if s]
        if segments and segments[0] not in RESERVED:
            return segments[0]
        return None

    # Tier 1: subdomain match
    for ats_host in SUBDOMAIN_HOSTS:
        if host == ats_host or host.endswith("." + ats_host):
            prefix = host[: -len(ats_host)].rstrip(".")
            if not prefix:
                return None
            first_label = prefix.split(".")[0]
            if first_label in RESERVED:
                return None
            return first_label

    return None
