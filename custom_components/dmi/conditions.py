"""Map DMI observations and forecast values to Home Assistant weather conditions.

DMI's metObs ``weather`` parameter carries a WMO present-weather code:

* 0-99 come from manned stations and follow WMO code table 4677 (``ww``).
* 100-199 come from automatic stations and follow WMO code table 4680
  (``wawa``) offset by 100, so ``100`` means "no significant weather observed".

See https://www.dmi.dk/friedata/dokumentation/meteorological-observations-data

Many codes describe something other than the current sky (cloud development,
weather during the preceding hour, haze). Those map to ``None`` so callers can
fall back to the observed cloud cover instead of guessing.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
)

# Hourly precipitation below this is a model trace, not rain worth an icon.
# 0.1 mm is the conventional threshold for measurable precipitation.
MIN_PRECIPITATION_MM = 0.1

# Cloud-cover thresholds (percent) used when no weather code decides the sky.
SUNNY_MAX_CLOUD_COVER = 20.0
PARTLYCLOUDY_MAX_CLOUD_COVER = 60.0


def _codes(codes: range | tuple[int, ...], condition: str) -> dict[int, str]:
    return dict.fromkeys(codes, condition)


# WMO 4680: present weather reported from an automatic station (DMI: code - 100).
WMO_4680_CONDITIONS: dict[int, str] = {
    # 00-04 no significant weather / cloud development / haze -> use cloud cover
    5: ATTR_CONDITION_FOG,  # haze, visibility below 1 km
    10: ATTR_CONDITION_FOG,  # mist
    11: ATTR_CONDITION_FOG,  # diamond dust
    12: ATTR_CONDITION_LIGHTNING,  # distant lightning
    18: ATTR_CONDITION_WINDY,  # squalls
    # 20-26 weather during the preceding hour, 27-29 blowing snow/sand -> cloud cover
    **_codes(range(30, 36), ATTR_CONDITION_FOG),
    40: ATTR_CONDITION_RAINY,  # precipitation
    41: ATTR_CONDITION_RAINY,
    42: ATTR_CONDITION_POURING,
    43: ATTR_CONDITION_RAINY,
    44: ATTR_CONDITION_POURING,
    45: ATTR_CONDITION_SNOWY,
    46: ATTR_CONDITION_SNOWY,
    47: ATTR_CONDITION_SNOWY_RAINY,  # freezing precipitation
    48: ATTR_CONDITION_SNOWY_RAINY,
    **_codes(range(50, 54), ATTR_CONDITION_RAINY),  # drizzle
    **_codes(range(54, 57), ATTR_CONDITION_SNOWY_RAINY),  # freezing drizzle
    57: ATTR_CONDITION_RAINY,  # drizzle and rain
    58: ATTR_CONDITION_RAINY,
    **_codes(range(60, 63), ATTR_CONDITION_RAINY),  # rain
    63: ATTR_CONDITION_POURING,  # heavy rain
    **_codes(range(64, 69), ATTR_CONDITION_SNOWY_RAINY),  # freezing rain, rain and snow
    **_codes(range(70, 74), ATTR_CONDITION_SNOWY),  # snow
    **_codes(range(74, 77), ATTR_CONDITION_HAIL),  # ice pellets
    77: ATTR_CONDITION_SNOWY,  # snow grains
    78: ATTR_CONDITION_SNOWY,  # ice crystals
    **_codes(range(80, 83), ATTR_CONDITION_RAINY),  # (rain) showers
    83: ATTR_CONDITION_POURING,  # heavy rain showers
    84: ATTR_CONDITION_POURING,  # violent rain showers
    **_codes(range(85, 88), ATTR_CONDITION_SNOWY),  # snow showers
    89: ATTR_CONDITION_HAIL,
    90: ATTR_CONDITION_LIGHTNING,  # thunderstorm
    91: ATTR_CONDITION_LIGHTNING,  # without precipitation
    92: ATTR_CONDITION_LIGHTNING_RAINY,  # with rain or snow showers
    93: ATTR_CONDITION_HAIL,  # with hail
    94: ATTR_CONDITION_LIGHTNING,  # heavy, without precipitation
    95: ATTR_CONDITION_LIGHTNING_RAINY,  # heavy, with rain or snow showers
    96: ATTR_CONDITION_HAIL,  # heavy, with hail
    99: ATTR_CONDITION_EXCEPTIONAL,  # tornado
}

# WMO 4677: present weather reported from a manned station.
WMO_4677_CONDITIONS: dict[int, str] = {
    # 00-03 cloud development, 04-09 haze/smoke/dust -> use cloud cover
    10: ATTR_CONDITION_FOG,  # mist
    11: ATTR_CONDITION_FOG,  # shallow fog
    12: ATTR_CONDITION_FOG,
    13: ATTR_CONDITION_LIGHTNING,  # lightning visible, no thunder
    # 14-16 precipitation within sight but not at the station -> cloud cover
    17: ATTR_CONDITION_LIGHTNING,  # thunderstorm without precipitation
    18: ATTR_CONDITION_WINDY,  # squalls
    19: ATTR_CONDITION_EXCEPTIONAL,  # funnel cloud
    # 20-29 weather during the preceding hour -> cloud cover
    **_codes(range(30, 36), ATTR_CONDITION_EXCEPTIONAL),  # dust or sand storm
    **_codes(range(36, 40), ATTR_CONDITION_SNOWY),  # drifting or blowing snow
    **_codes(range(40, 50), ATTR_CONDITION_FOG),
    **_codes(range(50, 56), ATTR_CONDITION_RAINY),  # drizzle
    56: ATTR_CONDITION_SNOWY_RAINY,  # freezing drizzle
    57: ATTR_CONDITION_SNOWY_RAINY,
    58: ATTR_CONDITION_RAINY,  # drizzle and rain
    59: ATTR_CONDITION_RAINY,
    **_codes(range(60, 64), ATTR_CONDITION_RAINY),  # rain
    64: ATTR_CONDITION_POURING,  # heavy rain
    65: ATTR_CONDITION_POURING,
    **_codes(range(66, 70), ATTR_CONDITION_SNOWY_RAINY),  # freezing rain, rain and snow
    **_codes(range(70, 79), ATTR_CONDITION_SNOWY),  # snow, snow grains, ice crystals
    79: ATTR_CONDITION_HAIL,  # ice pellets
    80: ATTR_CONDITION_RAINY,  # rain showers
    81: ATTR_CONDITION_RAINY,
    82: ATTR_CONDITION_POURING,  # violent rain showers
    83: ATTR_CONDITION_SNOWY_RAINY,  # rain and snow showers
    84: ATTR_CONDITION_SNOWY_RAINY,
    85: ATTR_CONDITION_SNOWY,  # snow showers
    86: ATTR_CONDITION_SNOWY,
    **_codes(range(87, 91), ATTR_CONDITION_HAIL),  # hail showers
    91: ATTR_CONDITION_RAINY,  # rain now, thunderstorm during the preceding hour
    92: ATTR_CONDITION_RAINY,
    93: ATTR_CONDITION_SNOWY,
    94: ATTR_CONDITION_SNOWY,
    95: ATTR_CONDITION_LIGHTNING_RAINY,  # thunderstorm with rain or snow
    96: ATTR_CONDITION_HAIL,  # thunderstorm with hail
    97: ATTR_CONDITION_LIGHTNING_RAINY,  # heavy thunderstorm
    98: ATTR_CONDITION_LIGHTNING,  # thunderstorm with dust or sand storm
    99: ATTR_CONDITION_HAIL,  # heavy thunderstorm with hail
}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def condition_from_weather_code(code: Any) -> str | None:
    """Return the condition a DMI present-weather code implies, if any."""
    number = _as_float(code)
    if number is None or not number.is_integer():
        return None
    code_int = int(number)
    if 100 <= code_int <= 199:
        return WMO_4680_CONDITIONS.get(code_int - 100)
    if 0 <= code_int <= 99:
        return WMO_4677_CONDITIONS.get(code_int)
    return None


def condition_from_cloud_cover(cloud_cover: Any, *, is_daytime: bool = True) -> str | None:
    """Return a sky condition for a cloud cover percentage."""
    cover = _as_float(cloud_cover)
    if cover is None:
        return None
    if cover < SUNNY_MAX_CLOUD_COVER:
        return ATTR_CONDITION_SUNNY if is_daytime else ATTR_CONDITION_CLEAR_NIGHT
    if cover < PARTLYCLOUDY_MAX_CLOUD_COVER:
        return ATTR_CONDITION_PARTLYCLOUDY
    return ATTR_CONDITION_CLOUDY


def forecast_condition(entry: dict[str, Any], *, is_daytime: bool = True) -> str | None:
    """Return the condition for one hourly forecast entry."""
    precipitation = _as_float(entry.get("precipitation"))
    if precipitation is not None and precipitation >= MIN_PRECIPITATION_MM:
        return ATTR_CONDITION_RAINY
    return condition_from_cloud_cover(entry.get("cloud_cover"), is_daytime=is_daytime)
