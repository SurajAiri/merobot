"""Runtime configuration loader for merobot.

Loads config.json once, resolves secret references from environment
variables, and exposes typed dataclasses via get_config().

Secret Resolution
-----------------
Values in config.json that look like ``UPPER_SNAKE_CASE`` strings
(e.g. ``"OPENAI_API_KEY"``) are treated as env-var references and
resolved from ``os.environ``.

To swap to a secret vault later, only ``resolve_secret()`` needs
to change — no other code is affected.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from merobot.constants import (
    CONFIG_FILENAME,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
    DEFAULT_WORKSPACE_DIR,
)

# Pattern to detect env-var-style values: UPPER_SNAKE_CASE with optional digits
_ENV_VAR_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


# ──────────────────────────────────────────────────────────────────────
# Secret Resolution
# ──────────────────────────────────────────────────────────────────────


def resolve_secret(value: str) -> str | None:
    """Resolve a potential secret reference.

    If ``value`` looks like an env-var name (UPPER_SNAKE_CASE),
    resolve it from os.environ.

    In the future, this is the single hook to swap in a vault
    (e.g. HashiCorp Vault, AWS Secrets Manager).

    Returns:
        The resolved secret string, or None if not found.
    """
    if not isinstance(value, str) or not value:
        return value

    if _ENV_VAR_PATTERN.match(value):
        resolved = os.environ.get(value)
        if resolved is None:
            logger.warning(
                f"Secret reference '{value}' not found in environment. "
                f"Set it in .env or export it."
            )
        return resolved

    # Literal value (not an env-var reference)
    return value


# ──────────────────────────────────────────────────────────────────────
# Config Dataclasses
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentDefaults:
    """Default LLM settings for the agent."""

    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS


@dataclass(frozen=True)
class AgentConfig:
    """Top-level agent configuration."""

    workspace_path: str = DEFAULT_WORKSPACE_DIR
    defaults: AgentDefaults = field(default_factory=AgentDefaults)

    @property
    def resolved_workspace(self) -> Path:
        """Return the workspace path as an absolute, expanded Path."""
        return Path(self.workspace_path).expanduser().resolve()


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for a single LLM provider."""

    name: str
    slug: str
    api_key: str | None = None  # Already resolved from env
    api_base: str = ""
    enabled: bool = False
    adapters: str = "openai"


@dataclass(frozen=True)
class ChannelConfig:
    """Configuration for a single communication channel."""

    name: str
    type: str
    enabled: bool = False
    token: str | None = None     # Already resolved from env
    user_id: str | None = None   # Already resolved from env
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    """Root config object holding all resolved configuration."""

    agent: AgentConfig
    providers: dict[str, ProviderConfig]
    channels: dict[str, ChannelConfig]

    def get_provider(self, slug: str) -> ProviderConfig | None:
        """Get a provider config by slug, or None if not found."""
        return self.providers.get(slug)

    def get_enabled_providers(self) -> dict[str, ProviderConfig]:
        """Return only enabled providers."""
        return {k: v for k, v in self.providers.items() if v.enabled}

    def get_channel(self, name: str) -> ChannelConfig | None:
        """Get a channel config by name, or None if not found."""
        return self.channels.get(name)

    def get_enabled_channels(self) -> dict[str, ChannelConfig]:
        """Return only enabled channels."""
        return {k: v for k, v in self.channels.items() if v.enabled}


# ──────────────────────────────────────────────────────────────────────
# Config Loading
# ──────────────────────────────────────────────────────────────────────

_config: AppConfig | None = None


def _find_project_root() -> Path:
    """Walk up from this file to find the project root (where configs/ lives)."""
    current = Path(__file__).resolve().parent
    for _ in range(10):  # safety limit
        if (current / "configs").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        f"Could not find project root (looked for 'configs/' directory "
        f"starting from {Path(__file__).resolve().parent})"
    )


def _load_raw_config() -> dict[str, Any]:
    """Load and return the raw config.json dict."""
    root = _find_project_root()
    config_path = root / CONFIG_FILENAME

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)

    logger.info(f"Loaded config from {config_path}")
    return data


def _parse_config(raw: dict[str, Any]) -> AppConfig:
    """Parse raw config dict into typed AppConfig."""

    # --- Agent ---
    agent_raw = raw.get("agent", {})
    defaults_raw = agent_raw.get("default", {})

    agent = AgentConfig(
        workspace_path=agent_raw.get("workspace_path", DEFAULT_WORKSPACE_DIR),
        defaults=AgentDefaults(
            provider=defaults_raw.get("provider", DEFAULT_PROVIDER),
            model=defaults_raw.get("model", DEFAULT_MODEL),
            temperature=defaults_raw.get("temperature", DEFAULT_TEMPERATURE),
            max_tokens=defaults_raw.get("max_tokens", DEFAULT_MAX_TOKENS),
        ),
    )

    # --- Providers ---
    providers: dict[str, ProviderConfig] = {}
    for slug, prov_raw in raw.get("providers", {}).items():
        api_key = resolve_secret(prov_raw.get("api_key", ""))
        providers[slug] = ProviderConfig(
            name=prov_raw.get("name", slug),
            slug=slug,
            api_key=api_key,
            enabled=prov_raw.get("enabled", False),
            api_base=prov_raw.get("api_base", ""),
            adapters=prov_raw.get("adapters", "openai"),
        )

    # --- Channels ---
    channels: dict[str, ChannelConfig] = {}
    for name, chan_raw in raw.get("channels", {}).items():
        token_key = chan_raw.get("env_token", "")
        user_id_key = chan_raw.get("env_user_id", "")

        channels[name] = ChannelConfig(
            name=name,
            type=chan_raw.get("type", name),
            enabled=chan_raw.get("enabled", False),
            token=resolve_secret(token_key) if token_key else None,
            user_id=resolve_secret(user_id_key) if user_id_key else None,
            extra={
                k: v for k, v in chan_raw.items()
                if k not in {"type", "enabled", "env_token", "env_user_id"}
            },
        )

    return AppConfig(agent=agent, providers=providers, channels=channels)


def get_config(*, reload: bool = False) -> AppConfig:
    """Return the singleton AppConfig, loading it on first call.

    Args:
        reload: Force re-read from disk (useful for testing).
    """
    global _config

    if _config is None or reload:
        from dotenv import load_dotenv

        load_dotenv()  # populate os.environ from .env

        raw = _load_raw_config()
        _config = _parse_config(raw)
        logger.debug(
            f"Config loaded: {len(_config.providers)} providers, "
            f"{len(_config.channels)} channels"
        )

    return _config
