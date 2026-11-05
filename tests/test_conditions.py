"""Tests for DMI weather-code and cloud-cover condition mapping."""

from __future__ import annotations

import pytest

from custom_components.dmi.conditions import (
    condition_from_cloud_cover,
    condition_from_weather_code,
    forecast_condition,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (100.0, None),  # automatic (WMO 4680 + 100): no significant weather -> cloud cover
        (110, "fog"),
        (163, "pouring"),
        (171, "snowy"),
        (192, "lightning-rainy"),
        (0, None),  # manned (WMO 4677): cloud development -> cloud cover
        (61, "rainy"),
        (95, "lightning-rainy"),
        ("invalid", None),
        (100.5, None),
        (999, None),
    ],
)
def test_condition_from_weather_code(code: object, expected: str | None) -> None:
    """Weather codes map through the WMO table matching their range."""
    assert condition_from_weather_code(code) == expected


def test_condition_from_cloud_cover() -> None:
    """Cloud cover thresholds respect day and night."""
    assert condition_from_cloud_cover(10.0) == "sunny"
    assert condition_from_cloud_cover(10.0, is_daytime=False) == "clear-night"
    assert condition_from_cloud_cover(20.0, is_daytime=False) == "partlycloudy"
    assert condition_from_cloud_cover(60.0) == "cloudy"
    assert condition_from_cloud_cover("x") is None


def test_forecast_condition_ignores_trace_precipitation() -> None:
    """Only measurable precipitation (>= 0.1 mm/h) makes a forecast hour rainy."""
    assert forecast_condition({"precipitation": 0.04, "cloud_cover": 10.0}) == "sunny"
    assert forecast_condition({"precipitation": 0.1, "cloud_cover": 10.0}) == "rainy"
    assert forecast_condition({}) is None
