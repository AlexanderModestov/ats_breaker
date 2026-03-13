"""Service for applying CSS-selector-based patches to HTML."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from hr_breaker.config import logger
from hr_breaker.models.editor import ResumePatch


def apply_patches(html: str, patches: list[ResumePatch]) -> str:
    """Apply a list of CSS-selector-based patches to *html* and return the modified markup.

    Each patch targets an element via its ``selector`` and performs the
    ``action`` (replace / append / prepend / remove).  If a selector doesn't
    match any element the patch is silently skipped with a warning log.
    """
    soup = BeautifulSoup(html, "html.parser")

    for patch in patches:
        element: Tag | None = soup.select_one(patch.selector)
        if element is None:
            logger.warning(
                "Patch selector %r matched no elements — skipping", patch.selector
            )
            continue

        if patch.action == "replace":
            new_tag = BeautifulSoup(patch.html or "", "html.parser")
            element.replace_with(new_tag)

        elif patch.action == "append":
            new_fragment = BeautifulSoup(patch.html or "", "html.parser")
            for child in list(new_fragment.children):
                element.append(child)

        elif patch.action == "prepend":
            new_fragment = BeautifulSoup(patch.html or "", "html.parser")
            # Insert children at position 0 in reverse order to preserve order
            for i, child in enumerate(list(new_fragment.children)):
                element.insert(i, child)

        elif patch.action == "remove":
            element.decompose()

    return str(soup)
