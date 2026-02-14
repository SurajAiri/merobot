"""Weather tool using wttr.in (free, no API key)."""

from typing import Any

import httpx
from loguru import logger

from merobot.tools.base import BaseTool

_WTTR_URL = "https://wttr.in"
_HEADERS = {"User-Agent": "merobot/0.1"}
_TIMEOUT = 10.0


class WeatherTool(BaseTool):
    """
    Get current weather and forecast for any location using wttr.in.
    No API key required.
    """

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return (
            "Get the current weather conditions and 3-day forecast "
            "for a given location. Supports city names, coordinates, "
            "or landmark names."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, coordinates, or landmark (e.g. 'Kathmandu', '27.7,85.3').",
                    "minLength": 1,
                    "maxLength": 200,
                },
                "units": {
                    "type": "string",
                    "description": "Unit system: 'metric' (°C, km/h) or 'imperial' (°F, mph). Default: metric.",
                    "enum": ["metric", "imperial"],
                },
            },
            "required": ["location"],
        }

    async def execute(self, **kwargs: Any) -> str:
        location: str = kwargs.get("location", "").strip()
        units: str = kwargs.get("units", "metric").strip()

        if not location:
            return "Error: 'location' parameter is required."

        logger.info(f"Weather lookup: {location!r} ({units})")

        try:
            data = await self._fetch_weather(location, units)
        except httpx.TimeoutException:
            return f"Error: Weather request timed out for '{location}'."
        except httpx.HTTPError as e:
            return f"Error: Could not fetch weather — {type(e).__name__}: {e}"
        except Exception as e:
            logger.error(f"Weather unexpected error: {e}")
            return f"Error: Unexpected error — {type(e).__name__}: {e}"

        return self._format_weather(location, data, units)

    async def _fetch_weather(self, location: str, units: str) -> dict:
        """Fetch weather JSON from wttr.in."""
        params = {"format": "j1"}
        if units == "imperial":
            params["u"] = ""  # use USCS units
        else:
            params["m"] = ""  # use metric units

        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                f"{_WTTR_URL}/{location}",
                params=params,
            )
            response.raise_for_status()

        return response.json()

    @staticmethod
    def _format_weather(location: str, data: dict, units: str) -> str:
        """Format wttr.in JSON into readable output."""
        try:
            current = data["current_condition"][0]
            area = data.get("nearest_area", [{}])[0]

            # Location info
            area_name = area.get("areaName", [{}])[0].get("value", location)
            country = area.get("country", [{}])[0].get("value", "")
            region = area.get("region", [{}])[0].get("value", "")
            loc_str = ", ".join(filter(None, [area_name, region, country]))

            # Current conditions
            temp_key = "temp_C" if units == "metric" else "temp_F"
            feels_key = "FeelsLikeC" if units == "metric" else "FeelsLikeF"
            temp_unit = "°C" if units == "metric" else "°F"
            wind_unit = "km/h" if units == "metric" else "mph"
            wind_key = "windspeedKmph" if units == "metric" else "windspeedMiles"

            desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")

            lines = [
                f"## Weather for {loc_str}\n",
                f"### Current Conditions",
                f"- **Condition**: {desc}",
                f"- **Temperature**: {current.get(temp_key, '?')}{temp_unit} "
                f"(feels like {current.get(feels_key, '?')}{temp_unit})",
                f"- **Humidity**: {current.get('humidity', '?')}%",
                f"- **Wind**: {current.get(wind_key, '?')} {wind_unit} "
                f"{current.get('winddir16Point', '')}",
                f"- **Visibility**: {current.get('visibility', '?')} km",
                f"- **UV Index**: {current.get('uvIndex', '?')}",
                "",
            ]

            # 3-day forecast
            forecast = data.get("weather", [])
            if forecast:
                lines.append("### 3-Day Forecast")
                for day in forecast[:3]:
                    date = day.get("date", "?")
                    max_key = "maxtempC" if units == "metric" else "maxtempF"
                    min_key = "mintempC" if units == "metric" else "mintempF"
                    desc_day = day.get("hourly", [{}])[4].get(
                        "weatherDesc", [{}]
                    )[0].get("value", "?") if len(day.get("hourly", [])) > 4 else "?"

                    lines.append(
                        f"- **{date}**: {desc_day}, "
                        f"{day.get(min_key, '?')}-{day.get(max_key, '?')}{temp_unit}"
                    )

            return "\n".join(lines)

        except (KeyError, IndexError, TypeError) as e:
            logger.warning(f"Failed to parse weather data: {e}")
            return f"Weather data received but could not be parsed. Raw: {str(data)[:500]}"
