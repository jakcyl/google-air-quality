"""Standalone CLI (`gaqi`) for querying the Google Air Quality API without Home Assistant."""

import argparse
import asyncio
import getpass
import json
import os
import sys
from typing import Any

import aiohttp

from .api import GoogleAirQualityClient, GoogleAirQualityError
from .const import SENSOR_KEYS
from .models import (
    POLLUTANT_KEYS,
    AirQualityData,
    AqiSource,
    CustomAqi,
    build_payload,
    parse_response,
    validate_custom_aqi,
)

DEFAULT_REQUESTABLE_SENSORS = POLLUTANT_KEYS | {"aqi", "health_recommendations"}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gaqi", description="Query the Google Air Quality API.")
    parser.add_argument("--api-key", help="API key (env: GOOGLE_AQI_API_KEY)")
    parser.add_argument("--lat", type=float, help="Latitude (env: GOOGLE_AQI_LAT)")
    parser.add_argument("--lon", type=float, help="Longitude (env: GOOGLE_AQI_LON)")
    parser.add_argument("--language", default="en", help="Language code (default: en)")
    parser.add_argument(
        "--source", choices=["universal", "regional"], default="universal", help="AQI source"
    )
    parser.add_argument("--region-code", help="Region code for a custom local AQI, e.g. IT")
    parser.add_argument("--local-aqi", help="Custom local AQI id, e.g. ita_moniqa")
    default_sensors = ",".join(sorted(DEFAULT_REQUESTABLE_SENSORS))
    parser.add_argument(
        "--sensors",
        help=f"Comma-separated sensors to request (default: {default_sensors})",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    return parser.parse_args(argv)


def _resolve_str(flag_value: str | None, env_var: str, prompt: str, *, secret: bool) -> str:
    if flag_value:
        return flag_value
    env_value = os.environ.get(env_var)
    if env_value:
        return env_value
    if sys.stdin.isatty():
        return getpass.getpass(f"{prompt}: ") if secret else input(f"{prompt}: ")
    print(
        f"Error: {prompt} not provided (use a flag, {env_var}, or an interactive terminal).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _resolve_float(flag_value: float | None, env_var: str, prompt: str) -> float:
    if flag_value is not None:
        return flag_value
    env_value = os.environ.get(env_var)
    if env_value:
        return float(env_value)
    if sys.stdin.isatty():
        return float(input(f"{prompt}: "))
    print(
        f"Error: {prompt} not provided (use a flag, {env_var}, or an interactive terminal).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _parse_sensors(raw: str | None) -> frozenset[str]:
    if raw is None:
        return frozenset(DEFAULT_REQUESTABLE_SENSORS)
    keys = frozenset(key.strip() for key in raw.split(","))
    unknown = keys - SENSOR_KEYS
    if unknown:
        print(f"Error: unknown sensor(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        raise SystemExit(1)
    return keys


def _format_table(data: AirQualityData) -> str:
    lines = [
        f"{'AQI':22}: {data.index.value} ({data.index.category})",
        f"{'Index':22}: {data.index.display_name} ({data.index.code})",
        f"{'Dominant pollutant':22}: {data.index.dominant_pollutant or '—'}",
    ]
    pollutant_units = {
        "pm25": "µg/m³",
        "pm10": "µg/m³",
        "co": "ppm",
        "no2": "µg/m³",
        "o3": "µg/m³",
        "so2": "µg/m³",
    }
    for key in sorted(data.pollutants):
        lines.append(f"{key:22}: {data.pollutants[key]} {pollutant_units[key]}")
    if data.health is not None:
        lines.append(f"{'Health recommendation':22}: {data.health['general_population']}")
    lines.append(f"{'Timestamp':22}: {data.timestamp.isoformat()}")
    return "\n".join(lines)


def _to_json_dict(data: AirQualityData) -> dict[str, Any]:
    return {
        "timestamp": data.timestamp.isoformat(),
        "index": {
            "code": data.index.code,
            "display_name": data.index.display_name,
            "value": data.index.value,
            "category": data.index.category,
            "dominant_pollutant": data.index.dominant_pollutant,
        },
        "pollutants": data.pollutants,
        "health": data.health,
    }


async def _run(
    args: argparse.Namespace, aqi_source: AqiSource, sensors: frozenset[str]
) -> AirQualityData:
    api_key = _resolve_str(args.api_key, "GOOGLE_AQI_API_KEY", "API key", secret=True)
    latitude = _resolve_float(args.lat, "GOOGLE_AQI_LAT", "Latitude")
    longitude = _resolve_float(args.lon, "GOOGLE_AQI_LON", "Longitude")
    custom_aqi = (
        CustomAqi(region_code=args.region_code, aqi=args.local_aqi) if args.region_code else None
    )

    payload = build_payload(latitude, longitude, aqi_source, sensors, args.language, custom_aqi)
    async with aiohttp.ClientSession() as session:
        client = GoogleAirQualityClient(session, api_key)
        raw = await client.current_conditions(payload)
    return parse_response(raw, aqi_source, sensors)


def main() -> None:
    """Console-script entry point."""
    args = _parse_args()
    try:
        aqi_source = AqiSource(args.source)
        sensors = _parse_sensors(args.sensors)
        validate_custom_aqi(aqi_source, args.region_code, args.local_aqi)
        data = asyncio.run(_run(args, aqi_source, sensors))
    except (GoogleAirQualityError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(_to_json_dict(data), indent=2))
    else:
        print(_format_table(data))
    sys.exit(0)


if __name__ == "__main__":
    main()
