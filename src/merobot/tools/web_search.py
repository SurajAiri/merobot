"""Web search tool using DuckDuckGo HTML endpoint."""

import re
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import httpx
from loguru import logger

from merobot.tools.base import BaseTool

_DDG_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}
_TIMEOUT = 15.0

# Regex patterns to extract results from DDG HTML
_RESULT_BLOCK = re.compile(
    r'<a\s+rel="nofollow"\s+class="result__a"\s+href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_SNIPPET_BLOCK = re.compile(
    r'<a\s+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    return unescape(_TAG_RE.sub("", text)).strip()


class WebSearchTool(BaseTool):
    """
    Search the web using DuckDuckGo.

    Returns formatted results with title, URL, and snippet.
    No API key required.
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for information. Returns titles, URLs, "
            "and snippets from top results. Use this when you need "
            "current information or facts you don't know."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up.",
                    "minLength": 1,
                    "maxLength": 500,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5).",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """
        Execute a web search and return formatted results.

        Args:
            query: The search query string.
            max_results: Max results to return (1-10, default 5).

        Returns:
            Formatted markdown string with search results,
            or an error message string on failure.
        """
        query: str = kwargs.get("query", "").strip()
        max_results: int = kwargs.get("max_results", 5)

        if not query:
            return "Error: 'query' parameter is required and cannot be empty."

        max_results = max(1, min(10, max_results))

        logger.info(f"Web search: {query!r} (max_results={max_results})")

        try:
            results = await self._fetch_results(query, max_results)
        except httpx.TimeoutException:
            logger.warning(f"Web search timed out for query: {query!r}")
            return f"Error: Search timed out for query '{query}'. Try again or simplify the query."
        except httpx.HTTPError as e:
            logger.error(f"Web search HTTP error for {query!r}: {e}")
            return f"Error: Could not complete web search — {type(e).__name__}: {e}"
        except Exception as e:
            logger.error(f"Web search unexpected error for {query!r}: {e}")
            return f"Error: Unexpected error during web search — {type(e).__name__}: {e}"

        if not results:
            return f"No results found for '{query}'."

        return self._format_results(query, results)

    async def _fetch_results(
        self, query: str, max_results: int
    ) -> list[dict[str, str]]:
        """Fetch search results from DuckDuckGo HTML endpoint."""
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.post(
                _DDG_URL,
                data={"q": query, "b": ""},
            )
            response.raise_for_status()

        html = response.text
        titles_urls = _RESULT_BLOCK.findall(html)
        snippets = _SNIPPET_BLOCK.findall(html)

        results: list[dict[str, str]] = []
        for i, (url, raw_title) in enumerate(titles_urls[:max_results]):
            title = _strip_html(raw_title)
            snippet = _strip_html(snippets[i]) if i < len(snippets) else ""

            # DDG wraps URLs in a redirect — extract the actual URL
            if "uddg=" in url:
                from urllib.parse import parse_qs, urlparse

                parsed = urlparse(url)
                qs = parse_qs(parsed.query)
                url = qs.get("uddg", [url])[0]

            results.append({
                "title": title,
                "url": url,
                "snippet": snippet,
            })

        return results

    @staticmethod
    def _format_results(query: str, results: list[dict[str, str]]) -> str:
        """Format search results as readable markdown."""
        lines = [f"## Search results for: {query}\n"]

        for i, r in enumerate(results, 1):
            lines.append(f"### {i}. {r['title']}")
            lines.append(f"**URL**: {r['url']}")
            if r["snippet"]:
                lines.append(f"{r['snippet']}")
            lines.append("")  # blank line between results

        return "\n".join(lines)
