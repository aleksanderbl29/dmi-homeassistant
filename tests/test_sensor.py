"""Tests for the DMI sensor entities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi.const import (
    CONF_BACKUP_PARAMETERS,
    CONF_BACKUP_STATION_NAME_SUFFIX,
    CONF_BACKUP_STATIONS,
    CONF_LOW_ASTRONOMICAL_TIDE,
    CONF_MEAN_LOW_WATER_SPRING,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_TIDEWATER_STATION_ID,
    CONF_TIDEWATER_STATION_NAME,
    DOMAIN,
    LAST_FETCH_SENSOR,
    SEA_SENSOR_TYPES,
    SENSOR_TYPES,
    TIDEWATER_SENSOR_TYPES,
)
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator
from custom_components.dmi.sensor import DMILastFetchSensor, DMISensor, DMITidewaterSensor


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
        assert sensor.name == "Solar Radiation"
        assert sensor.extra_state_attributes["source_type"] == "backup"
        assert "Composite Weather Station" in sensor.device_info["model"]

    def test_backup_sourced_name_suffix(
        self,
        mock_coordinator: MagicMock,
        mock_config_entry_options: dict[str, Any],
    ) -> None:
        """Test backup-sourced sensors can include the backup station name."""
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
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Landbohojskolen + backups",
            data={
                "setup_type": "advanced",
                CONF_STATION_ID: "06186",
                CONF_STATION_NAME: "Landbohojskolen",
                CONF_BACKUP_STATIONS: [
                    {
                        CONF_STATION_ID: "06187",
                        CONF_STATION_NAME: "Kobenhavns Toldbod",
                        CONF_BACKUP_PARAMETERS: ["radia_glob"],
                        CONF_BACKUP_STATION_NAME_SUFFIX: True,
                    }
                ],
            },
            options=mock_config_entry_options,
        )

        sensor = DMISensor(
            coordinator=mock_coordinator,
            config_entry=entry,
            entity_description=description,
        )

        assert sensor.name == "Solar Radiation - Kobenhavns Toldbod"


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


class TestDMITidewaterSensor:
    """Test astronomical tide prediction sensor behavior."""

    def test_predicted_level_exposes_series_and_extremes(self) -> None:
        """Test the main prediction sensor includes the rolling forecast."""
        coordinator = MagicMock(spec=DMIDataUpdateCoordinator)
        coordinator.data = {
            "tidewater_forecast": [
                {
                    "value": 12.1,
                    "prediction_time": "2026-07-25T09:40:00Z",
                    "prediction_type": "10minutes",
                    "created": "2026-03-23T10:18:26Z",
                    "station_id": "29393",
                },
                {
                    "value": 16.2,
                    "prediction_time": "2026-07-25T09:47:00Z",
                    "prediction_type": "maximum",
                    "created": "2026-03-23T09:30:10Z",
                    "station_id": "29393",
                },
                {
                    "value": -14.1,
                    "prediction_time": "2026-07-25T16:07:00Z",
                    "prediction_type": "minimum",
                    "created": "2026-03-23T09:30:10Z",
                    "station_id": "29393",
                },
            ],
            "last_updated": datetime(2026, 7, 25, 9, 35, tzinfo=UTC),
        }
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Korsør",
            data={
                "setup_type": "sea",
                CONF_STATION_ID: "30017",
                CONF_STATION_NAME: "Korsør",
                CONF_TIDEWATER_STATION_ID: "29393",
                CONF_TIDEWATER_STATION_NAME: "Korsør",
                CONF_LOW_ASTRONOMICAL_TIDE: -23.8,
                CONF_MEAN_LOW_WATER_SPRING: -15.0,
            },
        )
        description = next(
            item for item in TIDEWATER_SENSOR_TYPES if item.key == "predicted_sea_level"
        )

        sensor = DMITidewaterSensor(coordinator, entry, description)

        assert sensor.native_value == 12.1
        assert sensor.extra_state_attributes["prediction_time"] == ("2026-07-25T09:40:00Z")
        assert sensor.extra_state_attributes["forecast"] == [
            {"datetime": "2026-07-25T09:40:00Z", "value": 12.1}
        ]
        assert sensor.extra_state_attributes["next_high_tide"] == {
            "datetime": "2026-07-25T09:47:00Z",
            "value": 16.2,
        }
        assert sensor.extra_state_attributes["next_low_tide"] == {
            "datetime": "2026-07-25T16:07:00Z",
            "value": -14.1,
        }
        assert sensor.extra_state_attributes[CONF_LOW_ASTRONOMICAL_TIDE] == -23.8


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

    def test_sea_sensor_catalog_contains_all_ocean_parameters(self) -> None:
        """Test every documented ocean observation has a sensor definition."""
        assert {sensor.key for sensor in SEA_SENSOR_TYPES} == {
            "sealev_dvr",
            "sealev_ln",
            "sea_reg",
            "tw",
        }
        sea_level = next(s for s in SEA_SENSOR_TYPES if s.key == "sealev_dvr")
        water_temperature = next(s for s in SEA_SENSOR_TYPES if s.key == "tw")
        assert sea_level.native_unit_of_measurement == "cm"
        assert sea_level.device_class == SensorDeviceClass.DISTANCE
        assert water_temperature.native_unit_of_measurement == "°C"
        assert water_temperature.device_class == SensorDeviceClass.TEMPERATURE
        assert {sensor.key for sensor in TIDEWATER_SENSOR_TYPES} == {
            "predicted_sea_level",
            "next_high_tide",
            "next_low_tide",
        }


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

    async def test_dynamic_sensor_registration_on_coordinator_update(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test new parameters appear as sensors after a later coordinator refresh."""
        observation_payloads: dict[str, dict[str, Any]] = {
            "06180": {
                "temp_dry": {"value": 15.5, "observed": "2024-01-15T12:00:00Z"},
            },
        }

        async def get_observations(station_id: str) -> dict[str, Any]:
            return observation_payloads[station_id]

        mock_dmi_api.get_observations = AsyncMock(side_effect=get_observations)
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
        coordinator.api.get_observations = AsyncMock(side_effect=get_observations)

        assert hass.states.get("sensor.kobenhavns_lufthavn_temperature") is not None
        assert hass.states.get("sensor.kobenhavns_lufthavn_solar_radiation") is None

        observation_payloads["06180"]["radia_glob"] = {
            "value": 240.0,
            "observed": "2024-01-15T12:05:00Z",
        }
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert "radia_glob" in coordinator.data["observations"]
        entity_registry = er.async_get(hass)
        entity_id = entity_registry.async_get_entity_id(
            "sensor",
            DOMAIN,
            f"{mock_config_entry.entry_id}_radia_glob",
        )
        assert entity_id is not None
        assert hass.states.get(entity_id) is not None

    async def test_sea_entry_creates_all_available_ocean_sensors(
        self,
        hass: HomeAssistant,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test sea entries create sensors only for available ocean parameters."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Korsør",
            data={
                "setup_type": "sea",
                CONF_STATION_ID: "30017",
                CONF_STATION_NAME: "Korsør",
                CONF_TIDEWATER_STATION_ID: "29393",
                CONF_TIDEWATER_STATION_NAME: "Korsør",
                CONF_LOW_ASTRONOMICAL_TIDE: -23.8,
                CONF_MEAN_LOW_WATER_SPRING: -15.0,
                "latitude": 55.33,
                "longitude": 11.14,
                "use_coordinates": False,
            },
            options={"update_interval": 10, "include_forecast": True},
            unique_id="dmi_sea_30017",
        )
        mock_dmi_api.get_sea_observations = AsyncMock(
            return_value={
                "sealev_dvr": {
                    "value": 26.0,
                    "observed": "2026-07-24T15:40:00Z",
                    "created": "2026-07-24T15:41:44Z",
                    "qc_status": "auto",
                },
                "tw": {
                    "value": 18.2,
                    "observed": "2026-07-24T15:40:00Z",
                    "qc_status": "auto",
                },
            }
        )
        mock_dmi_api.get_tidewater_forecast = AsyncMock(
            return_value=[
                {
                    "value": 12.1,
                    "prediction_time": "2026-07-25T09:40:00Z",
                    "prediction_type": "10minutes",
                    "created": "2026-03-23T10:18:26Z",
                    "station_id": "29393",
                },
                {
                    "value": 16.2,
                    "prediction_time": "2026-07-25T09:47:00Z",
                    "prediction_type": "maximum",
                    "created": "2026-03-23T09:30:10Z",
                    "station_id": "29393",
                },
                {
                    "value": -14.1,
                    "prediction_time": "2026-07-25T16:07:00Z",
                    "prediction_type": "minimum",
                    "created": "2026-03-23T09:30:10Z",
                    "station_id": "29393",
                },
            ]
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        sea_level = hass.states.get("sensor.korsor_sea_level_dvr90")
        water_temperature = hass.states.get("sensor.korsor_water_temperature")
        predicted_level = hass.states.get("sensor.korsor_predicted_sea_level")
        next_high = hass.states.get("sensor.korsor_next_high_tide")
        next_low = hass.states.get("sensor.korsor_next_low_tide")
        assert sea_level is not None
        assert sea_level.state == "26.0"
        assert sea_level.attributes["quality_control_status"] == "auto"
        assert sea_level.attributes["created_time"] == "2026-07-24T15:41:44Z"
        assert water_temperature is not None
        assert predicted_level is not None
        assert predicted_level.state == "12.1"
        assert predicted_level.attributes["next_high_tide"]["value"] == 16.2
        assert next_high is not None
        assert next_high.state == "16.2"
        assert next_high.attributes["prediction_time"] == "2026-07-25T09:47:00Z"
        assert next_low is not None
        assert next_low.state == "-14.1"
        assert hass.states.get("weather.korsor") is None
        mock_dmi_api.get_observations.assert_not_called()
        mock_dmi_api.get_forecast.assert_not_called()
