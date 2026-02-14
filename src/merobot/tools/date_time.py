"""Current date/time tool using stdlib datetime + zoneinfo."""

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

from loguru import logger

from merobot.tools.base import BaseTool


class DateTimeTool(BaseTool):
    """
    Returns the current date and time with optional timezone
    and format customization.
    """

    @property
    def name(self) -> str:
        return "get_current_datetime"

    @property
    def description(self) -> str:
        return (
            "Get the current date and time. Supports any IANA timezone "
            "(e.g. 'Asia/Kolkata', 'US/Eastern', 'UTC') and custom "
            "strftime format strings."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "IANA timezone name (e.g. 'Asia/Kolkata', 'Europe/London'). "
                        "Defaults to 'UTC'."
                    ),
                },
                "format": {
                    "type": "string",
                    "description": (
                        "Python strftime format string. "
                        "Defaults to ISO 8601 ('%Y-%m-%dT%H:%M:%S%z')."
                    ),
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        tz_name: str = kwargs.get("timezone", "UTC").strip()
        fmt: str = kwargs.get("format", "%Y-%m-%dT%H:%M:%S%z").strip()

        # Resolve timezone
        try:
            tz = ZoneInfo(tz_name)
        except (KeyError, Exception):
            logger.warning(f"Invalid timezone: {tz_name!r}, falling back to UTC")
            return (
                f"Error: Unknown timezone '{tz_name}'. "
                f"Use IANA names like 'Asia/Kolkata', 'US/Eastern', 'UTC'."
            )

        now = datetime.now(tz)

        # Format the datetime
        try:
            formatted = now.strftime(fmt)
        except (ValueError, Exception) as e:
            logger.warning(f"Invalid format string: {fmt!r}: {e}")
            formatted = now.isoformat()

        # Build a rich response
        lines = [
            f"**Current Date & Time**",
            f"- **Formatted**: {formatted}",
            f"- **ISO 8601**: {now.isoformat()}",
            f"- **Timezone**: {tz_name} (UTC offset: {now.strftime('%z')})",
            f"- **Day of week**: {now.strftime('%A')}",
            f"- **Unix timestamp**: {int(now.timestamp())}",
        ]

        return "\n".join(lines)
