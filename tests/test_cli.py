"""Tests for cli.py: argument parsing, env fallback, and --json output."""

import json
import sys
from datetime import UTC, datetime

import pytest

from custom_components.google_air_quality_custom import cli
from custom_components.google_air_quality_custom.models import AirQualityData, AqiIndex


def test_parse_args_defaults() -> None:
    args = cli._parse_args([])
    assert args.language == "en"
    assert args.source == "universal"
    assert args.json is False


def test_parse_args_flags() -> None:
    args = cli._parse_args(
        ["--api-key", "k", "--lat", "1.5", "--lon", "2.5", "--source", "regional", "--json"]
    )
    assert args.api_key == "k"
    assert args.lat == 1.5
    assert args.lon == 2.5
    assert args.source == "regional"
    assert args.json is True


def test_resolve_str_prefers_flag_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_AQI_API_KEY", "from-env")
    assert (
        cli._resolve_str("from-flag", "GOOGLE_AQI_API_KEY", "API key", secret=True) == "from-flag"
    )


def test_resolve_str_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_AQI_API_KEY", "from-env")
    assert cli._resolve_str(None, "GOOGLE_AQI_API_KEY", "API key", secret=True) == "from-env"


def test_resolve_str_non_interactive_missing_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GOOGLE_AQI_API_KEY", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit) as exc_info:
        cli._resolve_str(None, "GOOGLE_AQI_API_KEY", "API key", secret=True)
    assert exc_info.value.code == 1
    assert "API key" in capsys.readouterr().err


def test_resolve_float_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_AQI_LAT", "45.5")
    assert cli._resolve_float(None, "GOOGLE_AQI_LAT", "Latitude") == 45.5


def test_parse_sensors_default_excludes_data_timestamp() -> None:
    sensors = cli._parse_sensors(None)
    assert "data_timestamp" not in sensors
    assert sensors == cli.DEFAULT_REQUESTABLE_SENSORS


def test_parse_sensors_unknown_key_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli._parse_sensors("aqi,bogus")
    assert exc_info.value.code == 1
    assert "bogus" in capsys.readouterr().err


def test_main_non_interactive_missing_key_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GOOGLE_AQI_API_KEY", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys, "argv", ["gaqi", "--lat", "1", "--lon", "2"])
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 1


def _sample_data() -> AirQualityData:
    return AirQualityData(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        index=AqiIndex(
            code="uaqi",
            display_name="Universal AQI",
            value=42,
            category="Good",
            dominant_pollutant="pm25",
        ),
        pollutants={"pm25": 8.6},
        health=None,
    )


def test_json_output_shape(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_run(args, aqi_source, sensors):
        return _sample_data()

    monkeypatch.setattr(cli, "_run", fake_run)
    monkeypatch.setattr(
        sys, "argv", ["gaqi", "--api-key", "k", "--lat", "1", "--lon", "2", "--json"]
    )
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["index"]["code"] == "uaqi"
    assert out["index"]["value"] == 42
    assert out["pollutants"] == {"pm25": 8.6}
    assert out["timestamp"] == "2026-01-01T00:00:00+00:00"


def test_table_output_is_human_readable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_run(args, aqi_source, sensors):
        return _sample_data()

    monkeypatch.setattr(cli, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["gaqi", "--api-key", "k", "--lat", "1", "--lon", "2"])
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "AQI" in out
    assert "42" in out
