"""Web scraping tool using httpx + BeautifulSoup."""

from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from merobot.constants import (
    DEFAULT_USER_AGENT,
    SCRAPE_ABSOLUTE_MAX_LENGTH,
    SCRAPE_DEFAULT_MAX_LENGTH,
    SCRAPE_STRIP_TAGS,
    SCRAPE_TIMEOUT,
)
from merobot.tools.base import BaseTool

_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class WebScrapeTool(BaseTool):
    """
    Fetch a web page and extract its readable text content.
    Strips scripts, styles, navigation, and other non-content elements.
    """

    @property
    def name(self) -> str:
        return "web_scrape"

    @property
    def description(self) -> str:
        return (
            "Fetch a web page and extract its readable text content. "
            "Use this to read articles, documentation, or any web page. "
            "Optionally target specific content with a CSS selector."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to scrape.",
                    "minLength": 1,
                },
                "max_length": {
                    "type": "integer",
                    "description": (
                        "Maximum characters of text to return. "
                        f"Default: {SCRAPE_DEFAULT_MAX_LENGTH}, max: {SCRAPE_ABSOLUTE_MAX_LENGTH}."
                    ),
                    "minimum": 100,
                    "maximum": SCRAPE_ABSOLUTE_MAX_LENGTH,
                    "default": SCRAPE_DEFAULT_MAX_LENGTH,
                },
                "selector": {
                    "type": "string",
                    "description": (
                        "Optional CSS selector to target specific content "
                        "(e.g. 'article', 'main', '.post-content'). "
                        "Falls back to full page if selector finds nothing."
                    ),
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> str:
        url: str = kwargs.get("url", "").strip()
        max_length: int = kwargs.get("max_length", SCRAPE_DEFAULT_MAX_LENGTH)
        selector: str | None = kwargs.get("selector")

        if not url:
            return "Error: 'url' parameter is required."

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            if not parsed.scheme:
                url = f"https://{url}"
            else:
                return f"Error: Unsupported URL scheme '{parsed.scheme}'. Use http or https."

        max_length = max(100, min(SCRAPE_ABSOLUTE_MAX_LENGTH, max_length))

        logger.info(f"Web scrape: {url!r} (max_length={max_length}, selector={selector!r})")

        try:
            html = await self._fetch_page(url)
        except httpx.TimeoutException:
            return f"Error: Request timed out for '{url}'."
        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} for '{url}'."
        except httpx.HTTPError as e:
            return f"Error: Could not fetch page — {type(e).__name__}: {e}"
        except Exception as e:
            logger.error(f"Web scrape unexpected error: {e}")
            return f"Error: Unexpected error — {type(e).__name__}: {e}"

        return self._extract_content(html, url, max_length, selector)

    async def _fetch_page(self, url: str) -> str:
        """Fetch HTML content from URL."""
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=SCRAPE_TIMEOUT,
            follow_redirects=True,
            max_redirects=5,
            verify=False,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                raise ValueError(f"Unsupported content type: {content_type}")

            return response.text

    def _extract_content(
        self, html: str, url: str, max_length: int, selector: str | None
    ) -> str:
        """Parse HTML and extract readable text."""
        soup = BeautifulSoup(html, "html.parser")

        title = soup.title.get_text(strip=True) if soup.title else ""
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag and meta_tag.get("content"):
            meta_desc = meta_tag["content"].strip()

        for tag_name in SCRAPE_STRIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        content_text = ""
        if selector:
            selected = soup.select(selector)
            if selected:
                content_text = "\n\n".join(
                    el.get_text(separator="\n", strip=True) for el in selected
                )

        if not content_text:
            body = soup.find("body")
            target = body if body else soup
            content_text = target.get_text(separator="\n", strip=True)

        lines = [line.strip() for line in content_text.splitlines()]
        lines = [line for line in lines if line]
        content_text = "\n".join(lines)

        truncated = False
        if len(content_text) > max_length:
            content_text = content_text[:max_length]
            truncated = True

        parts = [f"## Scraped: {title or url}\n"]
        if title:
            parts.append(f"**Title**: {title}")
        parts.append(f"**URL**: {url}")
        if meta_desc:
            parts.append(f"**Description**: {meta_desc}")
        parts.append(f"**Length**: {len(content_text)} chars")
        parts.append(f"\n---\n\n{content_text}")

        if truncated:
            parts.append(f"\n\n*[...truncated at {max_length} characters]*")

        return "\n".join(parts)
