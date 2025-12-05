"""Tests for the DMI sensor entities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi.const import CONF_STATION_ID, CONF_STATION_NAME, DOMAIN, SENSOR_TYPES
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator
from custom_components.dmi.sensor import DMISensor


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
    def humidity_sensor_description(self):
        """Get humidity sensor description."""
        return next(s for s in SENSOR_TYPES if s.key == "humidity")

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

    # --- Basic attribute tests ---

    def test_sensor_has_entity_name(
        self,
        temp_sensor: DMISensor,
    ) -> None:
        """Test sensor has entity name flag."""
        assert temp_sensor._attr_has_entity_name is True

    def test_sensor_unique_id(
        self,
        temp_sensor: DMISensor,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test sensor unique ID format."""
        assert temp_sensor._attr_unique_id == f"{mock_config_entry.entry_id}_temp_dry"

    def test_sensor_entity_description(
        self,
        temp_sensor: DMISensor,
        temp_sensor_description,
    ) -> None:
        """Test sensor has correct entity description."""
        assert temp_sensor.entity_description == temp_sensor_description
        assert temp_sensor.entity_description.key == "temp_dry"
        assert temp_sensor.entity_description.name == "Temperature"
        assert temp_sensor.entity_description.native_unit_of_measurement == "°C"
        assert temp_sensor.entity_description.device_class == SensorDeviceClass.TEMPERATURE
        assert temp_sensor.entity_description.state_class == SensorStateClass.MEASUREMENT

    def test_sensor_device_info(
        self,
        temp_sensor: DMISensor,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test sensor device info."""
        device_info = temp_sensor.device_info

        assert (DOMAIN, mock_config_entry.entry_id) in device_info["identifiers"]
        assert device_info["name"] == "Københavns Lufthavn"
        assert device_info["manufacturer"] == "Danish Meteorological Institute"
        assert "06180" in device_info["model"]
        assert device_info["configuration_url"] == "https://www.dmi.dk"

    # --- Value tests ---

    def test_native_value_temperature(
        self,
        temp_sensor: DMISensor,
    ) -> None:
        """Test temperature sensor value."""
        assert temp_sensor.native_value == 15.5

    def test_native_value_humidity(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
        humidity_sensor_description,
    ) -> None:
        """Test humidity sensor value."""
        sensor = DMISensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            entity_description=humidity_sensor_description,
        )
        assert sensor.native_value == 75.0

    def test_native_value_missing_parameter(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test sensor returns None for missing parameter."""
        # Get a sensor type that's not in the coordinator data
        radia_description = next(s for s in SENSOR_TYPES if s.key == "radia_glob")

        sensor = DMISensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            entity_description=radia_description,
        )
        assert sensor.native_value is None

    def test_native_value_no_coordinator_data(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
        temp_sensor_description,
    ) -> None:
        """Test sensor returns None when coordinator has no data."""
        mock_coordinator.data = None

        sensor = DMISensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            entity_description=temp_sensor_description,
        )
        assert sensor.native_value is None

    def test_native_value_empty_observations(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
        temp_sensor_description,
    ) -> None:
        """Test sensor returns None when observations are empty."""
        mock_coordinator.data = {"observations": {}}

        sensor = DMISensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            entity_description=temp_sensor_description,
        )
        assert sensor.native_value is None

    # --- Extra state attributes tests ---

    def test_extra_state_attributes(
        self,
        temp_sensor: DMISensor,
    ) -> None:
        """Test extra state attributes."""
        attrs = temp_sensor.extra_state_attributes

        assert "observation_time" in attrs
        assert attrs["observation_time"] == "2024-01-15T12:00:00Z"
        assert "last_updated" in attrs

    def test_extra_state_attributes_no_data(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
        temp_sensor_description,
    ) -> None:
        """Test extra attributes when no coordinator data."""
        mock_coordinator.data = None

        sensor = DMISensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            entity_description=temp_sensor_description,
        )
        attrs = sensor.extra_state_attributes

        assert attrs == {}

    def test_extra_state_attributes_no_observation_time(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry: MockConfigEntry,
        temp_sensor_description,
    ) -> None:
        """Test extra attributes when observation has no time."""
        mock_coordinator.data = {
            "observations": {
                "temp_dry": {"value": 15.5},  # No 'observed' key
            },
            "last_updated": datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        }

        sensor = DMISensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            entity_description=temp_sensor_description,
        )
        attrs = sensor.extra_state_attributes

        assert "observation_time" not in attrs
        assert "last_updated" in attrs

    def test_extra_state_attributes_last_updated_format(
        self,
        temp_sensor: DMISensor,
    ) -> None:
        """Test last_updated is formatted as ISO string."""
        attrs = temp_sensor.extra_state_attributes

        # Should be ISO format
        assert "last_updated" in attrs
        # Verify it's a valid ISO string (should contain 'T' for ISO format)
        assert "T" in attrs["last_updated"] or ":" in attrs["last_updated"]


class TestSensorTypes:
    """Test cases for SENSOR_TYPES definitions."""

    def test_sensor_types_count(self) -> None:
        """Test correct number of sensor types defined."""
        assert len(SENSOR_TYPES) == 11

    def test_all_sensor_types_have_required_fields(self) -> None:
        """Test all sensor types have required fields."""
        for sensor_type in SENSOR_TYPES:
            assert sensor_type.key is not None
            assert sensor_type.name is not None
            assert sensor_type.native_unit_of_measurement is not None

    def test_temperature_sensor_definition(self) -> None:
        """Test temperature sensor definition."""
        temp = next(s for s in SENSOR_TYPES if s.key == "temp_dry")
        assert temp.name == "Temperature"
        assert temp.native_unit_of_measurement == "°C"
        assert temp.device_class == SensorDeviceClass.TEMPERATURE
        assert temp.state_class == SensorStateClass.MEASUREMENT

    def test_humidity_sensor_definition(self) -> None:
        """Test humidity sensor definition."""
        humidity = next(s for s in SENSOR_TYPES if s.key == "humidity")
        assert humidity.name == "Humidity"
        assert humidity.native_unit_of_measurement == "%"
        assert humidity.device_class == SensorDeviceClass.HUMIDITY

    def test_pressure_sensor_definition(self) -> None:
        """Test pressure sensor definition."""
        pressure = next(s for s in SENSOR_TYPES if s.key == "pressure_at_sea")
        assert pressure.name == "Pressure"
        assert pressure.native_unit_of_measurement == "hPa"
        assert pressure.device_class == SensorDeviceClass.ATMOSPHERIC_PRESSURE

    def test_wind_speed_sensor_definition(self) -> None:
        """Test wind speed sensor definition."""
        wind = next(s for s in SENSOR_TYPES if s.key == "wind_speed")
        assert wind.name == "Wind Speed"
        assert wind.native_unit_of_measurement == "m/s"
        assert wind.device_class == SensorDeviceClass.WIND_SPEED

    def test_visibility_sensor_definition(self) -> None:
        """Test visibility sensor definition."""
        visibility = next(s for s in SENSOR_TYPES if s.key == "visibility")
        assert visibility.name == "Visibility"
        assert visibility.native_unit_of_measurement == "m"
        assert visibility.device_class == SensorDeviceClass.DISTANCE

    def test_precipitation_sensor_definition(self) -> None:
        """Test precipitation sensor definition."""
        precip = next(s for s in SENSOR_TYPES if s.key == "precip_past1h")
        assert precip.name == "Precipitation"
        assert precip.native_unit_of_measurement == "mm"
        assert precip.device_class == SensorDeviceClass.PRECIPITATION

    def test_cloud_cover_sensor_definition(self) -> None:
        """Test cloud cover sensor definition."""
        cloud = next(s for s in SENSOR_TYPES if s.key == "cloud_cover")
        assert cloud.name == "Cloud Cover"
        assert cloud.native_unit_of_measurement == "%"
        assert cloud.icon == "mdi:cloud"

    def test_solar_radiation_sensor_definition(self) -> None:
        """Test solar radiation sensor definition."""
        solar = next(s for s in SENSOR_TYPES if s.key == "radia_glob")
        assert solar.name == "Solar Radiation"
        assert solar.native_unit_of_measurement == "W/m²"
        assert solar.device_class == SensorDeviceClass.IRRADIANCE


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

        # Check temperature sensor exists
        temp_state = hass.states.get("sensor.kobenhavns_lufthavn_temperature")
        assert temp_state is not None
        assert float(temp_state.state) == 15.5

        # Check humidity sensor exists
        humidity_state = hass.states.get("sensor.kobenhavns_lufthavn_humidity")
        assert humidity_state is not None
        assert float(humidity_state.state) == 75.0
