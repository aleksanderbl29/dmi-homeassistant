"""Tests for the DMI sensor entities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi.const import DOMAIN, LAST_FETCH_SENSOR, SENSOR_TYPES
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator
from custom_components.dmi.sensor import DMILastFetchSensor, DMISensor


class TestDMISensor:
    """Test cases for DMISensor entity."""

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
    def temp_sensor_description(self):
        """Get temperature sensor description."""
        return next(s for s in SENSOR_TYPES if s.key == "temp_dry")

    @pytest.fixture
    def temp_sensor(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
        temp_sensor_description,
    ) -> DMISensor:
        """Create a temperature sensor instance."""
        return DMISensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            entity_description=temp_sensor_description,
        )

    def test_sensor_unique_id(
        self,
        temp_sensor: DMISensor,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test sensor unique ID format."""
        assert temp_sensor._attr_unique_id == f"{mock_config_entry.entry_id}_temp_dry"

    def test_sensor_device_info(
        self,
        temp_sensor: DMISensor,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test sensor device info."""
        device_info = temp_sensor.device_info

        assert (DOMAIN, mock_config_entry.entry_id) in device_info["identifiers"]
        assert device_info["name"] == "Københavns Lufthavn"
        assert "06180" in device_info["model"]

    def test_native_value_temperature(
        self,
        temp_sensor: DMISensor,
    ) -> None:
        """Test temperature sensor value."""
        assert temp_sensor.native_value == 15.5

    def test_extra_state_attributes_include_source(
        self,
        temp_sensor: DMISensor,
    ) -> None:
        """Test source attributes are exposed."""
        attrs = temp_sensor.extra_state_attributes

        assert attrs["source_station_id"] == "06180"
        assert attrs["source_station_name"] == "Kobenhavns Lufthavn"
        assert attrs["source_type"] == "primary"
        assert attrs["observation_time"] == "2024-01-15T12:00:00Z"
        assert "last_updated" in attrs

    def test_backup_sourced_attributes(
        self,
        mock_coordinator: MagicMock,
        advanced_config_entry: MockConfigEntry,
    ) -> None:
        """Test backup-sourced sensors expose backup source metadata."""
        description = next(s for s in SENSOR_TYPES if s.key == "radia_glob")
        mock_coordinator.data = {
            "observations": {
                "radia_glob": {
                    "value": 240.0,
                    "observed": "2024-01-15T12:00:00Z",
                    "source_station_id": "06187",
                    "source_station_name": "Kobenhavns Toldbod",
                    "source_type": "backup",
                }
            },
            "last_updated": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        }
        sensor = DMISensor(
            coordinator=mock_coordinator,
            config_entry=advanced_config_entry,
            entity_description=description,
        )

        assert sensor.native_value == 240.0
        assert sensor.extra_state_attributes["source_type"] == "backup"
        assert "Composite Weather Station" in sensor.device_info["model"]


class TestDMILastFetchSensor:
    """Test cases for the last-fetch diagnostic sensor."""

    @pytest.fixture
    def mock_coordinator(
        self,
        mock_coordinator_data: dict[str, Any],
    ) -> MagicMock:
        """Create a mock coordinator."""
        coordinator = MagicMock(spec=DMIDataUpdateCoordinator)
        coordinator.data = mock_coordinator_data
        return coordinator

    def test_last_fetch_sensor_native_value(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test last fetch sensor uses coordinator last_updated."""
        sensor = DMILastFetchSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
        )

        assert sensor.native_value == datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        assert sensor.entity_description == LAST_FETCH_SENSOR
        assert sensor.entity_description.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.entity_description.entity_category == EntityCategory.DIAGNOSTIC


class TestSensorTypes:
    """Test cases for SENSOR_TYPES definitions."""

    def test_sensor_catalog_contains_expanded_parameters(self) -> None:
        """Test the expanded sensor catalog includes advanced parameters."""
        keys = {sensor.key for sensor in SENSOR_TYPES}

        assert "temp_dry" in keys
        assert "pressure" in keys
        assert "radia_glob_past1h" in keys
        assert "sun_last1h_glob" in keys
        assert "weather" in keys
        assert len(SENSOR_TYPES) > 20

    def test_temperature_sensor_definition(self) -> None:
        """Test temperature sensor definition."""
        temp = next(s for s in SENSOR_TYPES if s.key == "temp_dry")
        assert temp.name == "Temperature"
        assert temp.native_unit_of_measurement == "°C"
        assert temp.device_class == SensorDeviceClass.TEMPERATURE
        assert temp.state_class == SensorStateClass.MEASUREMENT

    def test_weather_sensor_definition(self) -> None:
        """Test weather sensor definition."""
        weather = next(s for s in SENSOR_TYPES if s.key == "weather")
        assert weather.name == "Weather"
        assert weather.state_class is None


class TestDMISensorIntegration:
    """Integration tests for DMI sensor entities."""

    async def test_sensor_entities_created(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test sensor entities are created based on available parameters."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get("sensor.kobenhavns_lufthavn_temperature") is not None
        assert hass.states.get("sensor.kobenhavns_lufthavn_humidity") is not None

    async def test_advanced_entry_creates_enriched_sensor(
        self,
        hass: HomeAssistant,
        advanced_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test advanced entry exposes backup-only parameters."""
        advanced_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(advanced_config_entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.landbohojskolen_solar_radiation")
        assert state is not None
        assert state.attributes["source_station_id"] == "06187"
