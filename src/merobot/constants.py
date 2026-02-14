"""Compile-time constants for the merobot package.

These are values baked into code that change only on code updates,
NOT between environments. For runtime settings, see config.py.
"""

# ──────────────────────────────────────────────────────────────────────
# Tool: File Operations
# ──────────────────────────────────────────────────────────────────────
TOOL_MAX_READ_BYTES = 1 * 1024 * 1024       # 1 MB
TOOL_MAX_WRITE_BYTES = 5 * 1024 * 1024      # 5 MB
DEFAULT_WORKSPACE_DIR = "~/.merobot/workspace"

# ──────────────────────────────────────────────────────────────────────
# Tool: Web Scrape
# ──────────────────────────────────────────────────────────────────────
SCRAPE_TIMEOUT = 20.0
SCRAPE_DEFAULT_MAX_LENGTH = 5_000
SCRAPE_ABSOLUTE_MAX_LENGTH = 20_000
SCRAPE_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB max download
SCRAPE_STRIP_TAGS = [
    "script", "style", "noscript", "iframe", "svg",
    "nav", "footer", "header", "aside", "form",
]

# ──────────────────────────────────────────────────────────────────────
# Tool: Web Search
# ──────────────────────────────────────────────────────────────────────
SEARCH_TIMEOUT = 15.0
SEARCH_DDG_URL = "https://html.duckduckgo.com/html/"

# ──────────────────────────────────────────────────────────────────────
# Tool: Weather
# ──────────────────────────────────────────────────────────────────────
WEATHER_TIMEOUT = 10.0
WEATHER_URL = "https://wttr.in"

# ──────────────────────────────────────────────────────────────────────
# HTTP
# ──────────────────────────────────────────────────────────────────────
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ──────────────────────────────────────────────────────────────────────
# Agent Defaults (fallbacks if config.json is missing values)
# ──────────────────────────────────────────────────────────────────────
DEFAULT_PROVIDER = "litellm"
DEFAULT_MODEL = "gpt-3.5-turbo"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048

# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────
CONFIG_FILENAME = "configs/config.json"
