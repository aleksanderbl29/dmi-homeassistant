"""Fixtures and mock data for DMI Weather integration tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi.const import (
    CONF_INCLUDE_FORECAST,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_USE_COORDINATES,
    DOMAIN,
)

# Sample station data matching actual DMI API GeoJSON response format
# Based on: https://opendataapi.dmi.dk/v2/metObs/collections/station/items
MOCK_STATIONS_RESPONSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "f9eb71e9-063e-72ab-ca4a-3033e91559f9",
            "geometry": {
                "type": "Point",
                "coordinates": [12.6455, 55.614],  # [longitude, latitude]
            },
            "properties": {
                "owner": "Danske lufthavne",
                "country": "DNK",
                "anemometerHeight": None,
                "wmoCountryCode": "6080",
                "operationFrom": "1983-06-16T00:00:00Z",
                "parameterId": [
                    "cloud_cover", "cloud_height", "humidity", "precip_past1h",
                    "pressure", "pressure_at_sea", "temp_dew", "temp_dry",
                    "visibility", "weather", "wind_dir", "wind_max", "wind_speed"
                ],
                "created": "2025-06-23T06:18:29Z",
                "barometerHeight": None,
                "validFrom": "1983-06-16T00:00:00Z",
                "type": "Synop",
                "stationHeight": 5.0,
                "regionId": "6",
                "name": "Københavns Lufthavn",
                "wmoStationId": "06180",
                "operationTo": None,
                "updated": None,
                "stationId": "06180",
                "validTo": "2019-01-15T13:34:48Z",
                "status": "Active",
            },
        },
        {
            "type": "Feature",
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "geometry": {
                "type": "Point",
                "coordinates": [10.6195, 56.3031],
            },
            "properties": {
                "owner": "DMI",
                "country": "DNK",
                "anemometerHeight": None,
                "wmoCountryCode": "6080",
                "operationFrom": "1958-01-01T00:00:00Z",
                "parameterId": ["temp_dry", "humidity", "wind_speed", "pressure_at_sea"],
                "created": "2025-06-23T06:18:29Z",
                "barometerHeight": None,
                "validFrom": "1958-01-01T00:00:00Z",
                "type": "Synop",
                "stationHeight": 44.0,
                "regionId": "6",
                "name": "Aarhus Lufthavn",
                "wmoStationId": "06070",
                "operationTo": None,
                "updated": None,
                "stationId": "06070",
                "validTo": None,
                "status": "Active",
            },
        },
        {
            "type": "Feature",
            "id": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
            "geometry": {
                "type": "Point",
                "coordinates": [9.8494, 57.0928],
            },
            "properties": {
                "owner": "DMI",
                "country": "DNK",
                "anemometerHeight": None,
                "wmoCountryCode": "6080",
                "operationFrom": "1958-01-01T00:00:00Z",
                "parameterId": ["temp_dry", "humidity"],
                "created": "2025-06-23T06:18:29Z",
                "barometerHeight": None,
                "validFrom": "1958-01-01T00:00:00Z",
                "type": "Synop",
                "stationHeight": 3.0,
                "regionId": "6",
                "name": "Aalborg Lufthavn",
                "wmoStationId": "06060",
                "operationTo": None,
                "updated": None,
                "stationId": "06060",
                "validTo": None,
                "status": "Active",
            },
        },
    ],
    "timeStamp": "2024-01-15T12:00:00Z",
    "numberReturned": 3,
    "links": [
        {
            "href": "https://opendataapi.dmi.dk/v2/metObs/collections/station/items",
            "rel": "self",
            "type": "application/geo+json",
            "title": "This document",
        },
    ],
}

# Sample observations response matching actual DMI API format
# Based on: https://opendataapi.dmi.dk/v2/metObs/collections/observation/items
MOCK_OBSERVATIONS_RESPONSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "00ef883b-7f96-7a88-340d-3bbe98cc6fab",
            "geometry": {
                "type": "Point",
                "coordinates": [12.6454, 55.614],
            },
            "properties": {
                "parameterId": "temp_dry",
                "created": "2024-01-15T12:00:01.648483Z",
                "value": 15.5,
                "observed": "2024-01-15T12:00:00Z",
                "stationId": "06180",
            },
        },
        {
            "type": "Feature",
            "id": "25ac14c8-cc69-1f52-5db3-192f2311c183",
            "geometry": {
                "type": "Point",
                "coordinates": [12.6454, 55.614],
            },
            "properties": {
                "parameterId": "humidity",
                "created": "2024-01-15T12:00:01.649796Z",
                "value": 75.0,
                "observed": "2024-01-15T12:00:00Z",
                "stationId": "06180",
            },
        },
        {
            "type": "Feature",
            "id": "35d80b50-9864-3946-238e-6c68bbc3111a",
            "geometry": {
                "type": "Point",
                "coordinates": [12.6454, 55.614],
            },
            "properties": {
                "parameterId": "wind_speed",
                "created": "2024-01-15T12:00:01.651199Z",
                "value": 5.2,
                "observed": "2024-01-15T12:00:00Z",
                "stationId": "06180",
            },
        },
        {
            "type": "Feature",
            "id": "391d8ba1-62f6-ebd2-0396-e989f3be8369",
            "geometry": {
                "type": "Point",
                "coordinates": [12.6454, 55.614],
            },
            "properties": {
                "parameterId": "wind_dir",
                "created": "2024-01-15T12:00:01.651854Z",
                "value": 180.0,
                "observed": "2024-01-15T12:00:00Z",
                "stationId": "06180",
            },
        },
        {
            "type": "Feature",
            "id": "dd0b7ef5-1eb1-9d9d-9630-ed45b7240031",
            "geometry": {
                "type": "Point",
                "coordinates": [12.6454, 55.614],
            },
            "properties": {
                "parameterId": "pressure_at_sea",
                "created": "2024-01-15T12:00:01.652289Z",
                "value": 1013.25,
                "observed": "2024-01-15T12:00:00Z",
                "stationId": "06180",
            },
        },
        {
            "type": "Feature",
            "id": "ee1b8ef6-2fc2-0e0e-0741-fe56b8351142",
            "geometry": {
                "type": "Point",
                "coordinates": [12.6454, 55.614],
            },
            "properties": {
                "parameterId": "visibility",
                "created": "2024-01-15T12:00:01.653000Z",
                "value": 10000,
                "observed": "2024-01-15T12:00:00Z",
                "stationId": "06180",
            },
        },
        {
            "type": "Feature",
            "id": "ff2c9fg7-3gd3-1f1f-1852-gf67c9462253",
            "geometry": {
                "type": "Point",
                "coordinates": [12.6454, 55.614],
            },
            "properties": {
                "parameterId": "cloud_cover",
                "created": "2024-01-15T12:00:01.654000Z",
                "value": 50.0,
                "observed": "2024-01-15T12:00:00Z",
                "stationId": "06180",
            },
        },
    ],
    "timeStamp": "2024-01-15T12:00:09Z",
    "numberReturned": 7,
    "links": [
        {
            "href": "https://opendataapi.dmi.dk/v2/metObs/collections/observation/items?stationId=06180",
            "rel": "self",
            "type": "application/geo+json",
            "title": "This document",
        },
    ],
}

# Sample forecast response matching actual DMI API CoverageJSON format
# Based on: https://opendataapi.dmi.dk/v1/forecastedr/collections/harmonie_dini_sf/position
MOCK_FORECAST_RESPONSE = {
    "type": "Coverage",
    "title": {
        "en": "Grid Feature",
    },
    "domain": {
        "type": "Domain",
        "domainType": "Grid",
        "axes": {
            "t": {
                "values": [
                    "2024-01-15T12:00:00.000Z",
                    "2024-01-15T13:00:00.000Z",
                    "2024-01-15T14:00:00.000Z",
                    "2024-01-15T15:00:00.000Z",
                ],
            },
            "x": {
                "values": [12.562736751058935],
                "bounds": [12.562736751058935, 12.562736751058935],
            },
            "y": {
                "values": [55.68035305486726],
                "bounds": [55.68035305486726, 55.68035305486726],
            },
        },
        "referencing": [
            {
                "coordinates": ["x", "y"],
                "system": {
                    "type": "GeographicCRS",
                    "id": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                },
            },
            {
                "coordinates": ["t"],
                "system": {
                    "type": "TemporalRS",
                    "calendar": "Gregorian",
                },
            },
        ],
    },
    "parameters": {
        "temperature-2m": {
            "type": "Parameter",
            "description": {
                "en": "Temperature in 2m height",
            },
            "observedProperty": {
                "label": {
                    "en": "https://apps.ecmwf.int/codes/grib/param-db?id=167",
                },
            },
        },
        "wind-speed-10m": {
            "type": "Parameter",
            "description": {
                "en": "The speed of horizontal air movement in metres per second at 10m.",
            },
            "observedProperty": {
                "label": {
                    "en": "https://apps.ecmwf.int/codes/grib/param-db?id=10",
                },
            },
        },
    },
    "ranges": {
        "temperature-2m": {
            "type": "NdArray",
            "dataType": "float",
            "axisNames": ["t", "y", "x"],
            "shape": [4, 1, 1],
            "values": [288.65, 289.15, 290.15, 289.65],  # Kelvin
        },
        "wind-speed-10m": {
            "type": "NdArray",
            "dataType": "float",
            "axisNames": ["t", "y", "x"],
            "shape": [4, 1, 1],
            "values": [5.0, 5.5, 6.0, 5.8],
        },
        "wind-dir-10m": {
            "type": "NdArray",
            "dataType": "float",
            "axisNames": ["t", "y", "x"],
            "shape": [4, 1, 1],
            "values": [180, 185, 190, 188],
        },
        "relative-humidity": {
            "type": "NdArray",
            "dataType": "float",
            "axisNames": ["t", "y", "x"],
            "shape": [4, 1, 1],
            "values": [75.0, 73.0, 70.0, 72.0],
        },
        "total-precipitation": {
            "type": "NdArray",
            "dataType": "float",
            "axisNames": ["t", "y", "x"],
            "shape": [4, 1, 1],
            "values": [0.0, 0.1, 0.2, 0.0],
        },
        "cloud-cover": {
            "type": "NdArray",
            "dataType": "float",
            "axisNames": ["t", "y", "x"],
            "shape": [4, 1, 1],
            "values": [50.0, 60.0, 70.0, 65.0],
        },
    },
}


@pytest.fixture
def mock_stations_data() -> dict[str, Any]:
    """Return mock stations API response."""
    return MOCK_STATIONS_RESPONSE


@pytest.fixture
def mock_observations_data() -> dict[str, Any]:
    """Return mock observations API response."""
    return MOCK_OBSERVATIONS_RESPONSE


@pytest.fixture
def mock_forecast_data() -> dict[str, Any]:
    """Return mock forecast API response."""
    return MOCK_FORECAST_RESPONSE


@pytest.fixture
def mock_config_entry_data() -> dict[str, Any]:
    """Return mock config entry data."""
    return {
        CONF_STATION_ID: "06180",
        CONF_STATION_NAME: "Københavns Lufthavn",
        "latitude": 55.614,
        "longitude": 12.6455,
        CONF_USE_COORDINATES: False,
    }


@pytest.fixture
def mock_config_entry_options() -> dict[str, Any]:
    """Return mock config entry options."""
    return {
        CONF_UPDATE_INTERVAL: 10,
        CONF_INCLUDE_FORECAST: True,
    }


@pytest.fixture
def mock_config_entry(
    mock_config_entry_data: dict[str, Any],
    mock_config_entry_options: dict[str, Any],
) -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Københavns Lufthavn",
        data=mock_config_entry_data,
        options=mock_config_entry_options,
        unique_id="dmi_06180",
        version=1,
    )


@pytest.fixture
def mock_coordinator_data() -> dict[str, Any]:
    """Return mock coordinator data (processed API response)."""
    return {
        "observations": {
            "temp_dry": {"value": 15.5, "observed": "2024-01-15T12:00:00Z"},
            "humidity": {"value": 75.0, "observed": "2024-01-15T12:00:00Z"},
            "wind_speed": {"value": 5.2, "observed": "2024-01-15T12:00:00Z"},
            "wind_dir": {"value": 180.0, "observed": "2024-01-15T12:00:00Z"},
            "pressure_at_sea": {"value": 1013.25, "observed": "2024-01-15T12:00:00Z"},
            "visibility": {"value": 10000, "observed": "2024-01-15T12:00:00Z"},
            "cloud_cover": {"value": 50.0, "observed": "2024-01-15T12:00:00Z"},
        },
        "forecast": {
            "hourly": [
                {
                    "datetime": "2024-01-15T12:00:00Z",
                    "temperature": 15.5,  # Converted from Kelvin
                    "wind_speed": 5.0,
                    "wind_dir": 180,
                    "humidity": 75.0,
                    "precipitation": 0.0,
                    "cloud_cover": 50.0,
                },
                {
                    "datetime": "2024-01-15T13:00:00Z",
                    "temperature": 16.0,
                    "wind_speed": 5.5,
                    "wind_dir": 185,
                    "humidity": 73.0,
                    "precipitation": 0.1,
                    "cloud_cover": 60.0,
                },
            ],
        },
        "last_updated": datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Create a mock API client with realistic response data."""
    client = MagicMock()

    # Return processed station data (as the API client returns after parsing)
    client.get_stations = AsyncMock(return_value=[
        {
            "stationId": "06180",
            "name": "Københavns Lufthavn",
            "latitude": 55.614,
            "longitude": 12.6455,
            "type": "Synop",
            "parameterId": [
                "cloud_cover", "humidity", "pressure_at_sea", "temp_dry",
                "visibility", "wind_dir", "wind_speed"
            ],
        },
        {
            "stationId": "06070",
            "name": "Aarhus Lufthavn",
            "latitude": 56.3031,
            "longitude": 10.6195,
            "type": "Synop",
            "parameterId": ["temp_dry", "humidity", "wind_speed", "pressure_at_sea"],
        },
    ])

    # Return processed observation data (keyed by parameterId)
    client.get_observations = AsyncMock(return_value={
        "temp_dry": {"value": 15.5, "observed": "2024-01-15T12:00:00Z"},
        "humidity": {"value": 75.0, "observed": "2024-01-15T12:00:00Z"},
        "wind_speed": {"value": 5.2, "observed": "2024-01-15T12:00:00Z"},
        "wind_dir": {"value": 180.0, "observed": "2024-01-15T12:00:00Z"},
        "pressure_at_sea": {"value": 1013.25, "observed": "2024-01-15T12:00:00Z"},
        "cloud_cover": {"value": 50.0, "observed": "2024-01-15T12:00:00Z"},
    })

    # Return processed forecast data (with temperature converted from Kelvin)
    client.get_forecast = AsyncMock(return_value={
        "hourly": [
            {
                "datetime": "2024-01-15T12:00:00.000Z",
                "temperature": 15.5,  # 288.65K - 273.15
                "wind_speed": 5.0,
                "wind_dir": 180,
                "humidity": 75.0,
                "precipitation": 0.0,
                "cloud_cover": 50.0,
            },
        ],
    })

    client.test_connection = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_dmi_api(mock_api_client: MagicMock) -> Generator[MagicMock, None, None]:
    """Mock the DMI API client."""
    with patch(
        "custom_components.dmi.DMIApiClient",
        return_value=mock_api_client,
    ), patch(
        "custom_components.dmi.config_flow.DMIApiClient",
        return_value=mock_api_client,
    ):
        yield mock_api_client


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None, None, None]:
    """Automatically enable custom integrations for all tests."""
    yield
