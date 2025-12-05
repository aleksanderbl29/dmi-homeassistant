"""Tests for the DMI Weather entity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.const import UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi.const import CONF_STATION_ID, CONF_STATION_NAME, DOMAIN
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator
from custom_components.dmi.weather import DMIWeather


class TestDMIWeather:
    """Test cases for DMIWeather entity."""

    @pytest.fixture
    def mock_coordinator(
        self,
        mock_coordinator_data: dict[str, Any],
    ) -> MagicMock:
        """Create a mock coordinator."""
        coordinator = MagicMock(spec=DMIDataUpdateCoordinator)
        coordinator.data = mock_coordinator_data
        return coordinator

    @pytest.fixture
    def weather_entity(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> DMIWeather:
        """Create a weather entity instance."""
        return DMIWeather(mock_coordinator, mock_config_entry)

    # --- Basic attribute tests ---

    def test_entity_attributes(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test basic entity attributes."""
        assert weather_entity._attr_has_entity_name is True
        assert weather_entity._attr_name is None
        assert weather_entity._attr_native_temperature_unit == UnitOfTemperature.CELSIUS
        assert weather_entity._attr_native_pressure_unit == UnitOfPressure.HPA
        assert weather_entity._attr_native_wind_speed_unit == UnitOfSpeed.METERS_PER_SECOND
        assert WeatherEntityFeature.FORECAST_HOURLY in weather_entity._attr_supported_features

    def test_unique_id(
        self,
        weather_entity: DMIWeather,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test unique ID is set correctly."""
        assert weather_entity._attr_unique_id == f"{mock_config_entry.entry_id}_weather"

    def test_device_info(
        self,
        weather_entity: DMIWeather,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test device info is correct."""
        device_info = weather_entity.device_info

        assert (DOMAIN, mock_config_entry.entry_id) in device_info["identifiers"]
        assert device_info["name"] == "Københavns Lufthavn"
        assert device_info["manufacturer"] == "Danish Meteorological Institute"
        assert "06180" in device_info["model"]
        assert device_info["configuration_url"] == "https://www.dmi.dk"

    # --- Current conditions tests ---

    def test_native_temperature(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test temperature reading."""
        assert weather_entity.native_temperature == 15.5

    def test_humidity(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test humidity reading."""
        assert weather_entity.humidity == 75.0

    def test_native_pressure(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test pressure reading."""
        assert weather_entity.native_pressure == 1013.25

    def test_native_wind_speed(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test wind speed reading."""
        assert weather_entity.native_wind_speed == 5.2

    def test_wind_bearing(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test wind bearing reading."""
        assert weather_entity.wind_bearing == 180.0

    def test_native_visibility(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test visibility reading (converted from m to km)."""
        assert weather_entity.native_visibility == 10.0

    def test_visibility_none_when_missing(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test visibility returns None when not available."""
        mock_coordinator.data = {"observations": {}}
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.native_visibility is None

    def test_visibility_handles_invalid_value(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test visibility handles invalid value gracefully."""
        mock_coordinator.data = {
            "observations": {
                "visibility": {"value": "invalid"},
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.native_visibility is None

    # --- Condition tests ---

    def test_condition_from_weather_code(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test condition mapping from weather code."""
        mock_coordinator.data = {
            "observations": {
                "weather": {"value": 3},  # Cloudy
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "cloudy"

    def test_condition_sunny_from_code(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test sunny condition from weather code."""
        mock_coordinator.data = {
            "observations": {
                "weather": {"value": 0},
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "sunny"

    def test_condition_rainy_from_code(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test rainy condition from weather code."""
        mock_coordinator.data = {
            "observations": {
                "weather": {"value": 61},
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "rainy"

    def test_condition_from_cloud_cover_sunny(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test condition fallback to cloud cover - sunny."""
        mock_coordinator.data = {
            "observations": {
                "cloud_cover": {"value": 10.0},
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "sunny"

    def test_condition_from_cloud_cover_partly_cloudy(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test condition fallback to cloud cover - partlycloudy."""
        mock_coordinator.data = {
            "observations": {
                "cloud_cover": {"value": 50.0},
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "partlycloudy"

    def test_condition_from_cloud_cover_cloudy(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test condition fallback to cloud cover - cloudy."""
        mock_coordinator.data = {
            "observations": {
                "cloud_cover": {"value": 80.0},
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "cloudy"

    def test_condition_default_cloudy(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test condition defaults to cloudy when no data."""
        mock_coordinator.data = {"observations": {}}
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "cloudy"

    def test_condition_handles_invalid_weather_code(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test condition handles invalid weather code gracefully."""
        mock_coordinator.data = {
            "observations": {
                "weather": {"value": "invalid"},
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "cloudy"

    def test_condition_unknown_code_defaults_to_cloudy(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test unknown weather code defaults to cloudy."""
        mock_coordinator.data = {
            "observations": {
                "weather": {"value": 999},  # Unknown code
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity.condition == "cloudy"

    # --- Observations handling tests ---

    def test_observations_returns_empty_when_no_data(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test observations returns empty dict when no data."""
        mock_coordinator.data = None
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        assert entity._observations == {}

    def test_get_observation_value_returns_none_for_missing(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test observation value returns None for missing key."""
        assert weather_entity._get_observation_value("nonexistent") is None

    # --- Forecast tests ---

    async def test_async_forecast_hourly(
        self,
        weather_entity: DMIWeather,
    ) -> None:
        """Test hourly forecast generation."""
        forecasts = await weather_entity.async_forecast_hourly()

        assert forecasts is not None
        assert len(forecasts) == 2

        first_forecast = forecasts[0]
        assert first_forecast["datetime"] == "2024-01-15T12:00:00Z"
        assert first_forecast["native_temperature"] == 15.5
        assert first_forecast["native_wind_speed"] == 5.0
        assert first_forecast["wind_bearing"] == 180
        assert first_forecast["humidity"] == 75.0
        assert first_forecast["native_precipitation"] == 0.0
        assert first_forecast["condition"] == "partlycloudy"  # 50% cloud cover

    async def test_async_forecast_hourly_condition_sunny(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test forecast condition sunny for low cloud cover."""
        mock_coordinator.data = {
            "observations": {},
            "forecast": {
                "hourly": [
                    {
                        "datetime": "2024-01-15T12:00:00Z",
                        "cloud_cover": 10.0,
                    },
                ],
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        forecasts = await entity.async_forecast_hourly()

        assert forecasts[0]["condition"] == "sunny"

    async def test_async_forecast_hourly_condition_cloudy(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test forecast condition cloudy for high cloud cover."""
        mock_coordinator.data = {
            "observations": {},
            "forecast": {
                "hourly": [
                    {
                        "datetime": "2024-01-15T12:00:00Z",
                        "cloud_cover": 80.0,
                    },
                ],
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        forecasts = await entity.async_forecast_hourly()

        assert forecasts[0]["condition"] == "cloudy"

    async def test_async_forecast_hourly_no_data(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test hourly forecast returns None when no coordinator data."""
        mock_coordinator.data = None
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        forecasts = await entity.async_forecast_hourly()

        assert forecasts is None

    async def test_async_forecast_hourly_no_forecast(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test hourly forecast returns None when no forecast data."""
        mock_coordinator.data = {"observations": {}, "forecast": None}
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        forecasts = await entity.async_forecast_hourly()

        assert forecasts is None

    async def test_async_forecast_hourly_empty_hourly(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test hourly forecast returns None when hourly list is empty."""
        mock_coordinator.data = {
            "observations": {},
            "forecast": {"hourly": []},
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        forecasts = await entity.async_forecast_hourly()

        assert forecasts is None

    async def test_async_forecast_hourly_partial_data(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test forecast with partial data (missing fields)."""
        mock_coordinator.data = {
            "observations": {},
            "forecast": {
                "hourly": [
                    {
                        "datetime": "2024-01-15T12:00:00Z",
                        "temperature": 15.5,
                        # Missing other fields
                    },
                ],
            },
        }
        entity = DMIWeather(mock_coordinator, mock_config_entry)

        forecasts = await entity.async_forecast_hourly()

        assert forecasts is not None
        assert len(forecasts) == 1
        assert forecasts[0]["native_temperature"] == 15.5
        assert "native_wind_speed" not in forecasts[0]


class TestDMIWeatherIntegration:
    """Integration tests for DMI Weather entity."""

    async def test_weather_entity_state(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test weather entity is created with correct state."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("weather.kobenhavns_lufthavn")
        assert state is not None
        assert state.state == "partlycloudy"  # Based on 50% cloud cover
        assert state.attributes["temperature"] == 15.5
        assert state.attributes["humidity"] == 75.0
