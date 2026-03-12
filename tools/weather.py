"""Cached Open-Meteo weather lookup."""

from __future__ import annotations

import asyncio
import time
from datetime import date as date_type
from typing import Optional


WEATHER_SCHEMA = {
    "name": "get_weather",
    "description": "Get current conditions or a daily forecast for a city using Open-Meteo.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"city": {"type": "string"}, "date": {"type": "string"}},
        "required": ["city"],
    },
}


_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = asyncio.Lock()


async def get_weather(city: str, date: Optional[str] = None) -> dict:
    target_date = date or date_type.today().isoformat()
    try:
        date_type.fromisoformat(target_date)
    except ValueError:
        return {"ok": False, "error": "Date must use YYYY-MM-DD"}
    import httpx

    key = (city.strip().lower(), target_date)
    async with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > time.monotonic():
            return {**cached[1], "cached": True}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client, asyncio.timeout(6):
            geocoding = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "en", "format": "json"},
            )
            geocoding.raise_for_status()
            locations = geocoding.json().get("results", [])
            if not locations:
                return {"ok": False, "error": f"No weather location found for {city}"}
            location = locations[0]
            forecast = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": location["latitude"], "longitude": location["longitude"],
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto", "forecast_days": 16,
                },
            )
            forecast.raise_for_status()
            daily = forecast.json()["daily"]
            if target_date not in daily["time"]:
                return {"ok": False, "error": "Forecast date is outside the available 16-day window"}
            index = daily["time"].index(target_date)
            result = {
                "ok": True,
                "city": location["name"], "country": location.get("country"), "date": target_date,
                "weather_code": daily["weather_code"][index],
                "temperature_min_c": daily["temperature_2m_min"][index],
                "temperature_max_c": daily["temperature_2m_max"][index],
                "precipitation_probability_percent": daily["precipitation_probability_max"][index],
                "source": "Open-Meteo",
            }
    except (httpx.HTTPError, TimeoutError) as exc:
        return {"ok": False, "error": f"Weather service unavailable: {type(exc).__name__}"}

    async with _cache_lock:
        _cache[key] = (time.monotonic() + 600, result)
    return result
