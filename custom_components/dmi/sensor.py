"""Sensor platform for DMI Weather integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_BACKUP_STATION_NAME_SUFFIX,
    CONF_BACKUP_STATIONS,
    CONF_LOW_ASTRONOMICAL_TIDE,
    CONF_MEAN_LOW_WATER_SPRING,
    CONF_SETUP_TYPE,
    CONF_SOURCE_STATION_ID,
    CONF_SOURCE_STATION_NAME,
    CONF_SOURCE_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_TIDEWATER_STATION_ID,
    CONF_TIDEWATER_STATION_NAME,
    DOMAIN,
    LAST_FETCH_SENSOR,
    SEA_SENSOR_TYPES,
    SEA_SENSOR_TYPES_BY_KEY,
    SENSOR_TYPES,
    SENSOR_TYPES_BY_KEY,
    SETUP_TYPE_ADVANCED,
    SETUP_TYPE_SEA,
    SOURCE_TYPE_BACKUP,
    TIDEWATER_SENSOR_TYPES,
)
from .coordinator import DMIDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DMI Weather sensor entities from config entry."""
    coordinator: DMIDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensor_types = SEA_SENSOR_TYPES if coordinator.setup_type == SETUP_TYPE_SEA else SENSOR_TYPES
    sensor_types_by_key = (
        SEA_SENSOR_TYPES_BY_KEY if coordinator.setup_type == SETUP_TYPE_SEA else SENSOR_TYPES_BY_KEY
    )
    observations = coordinator.data.get("observations", {}) if coordinator.data else {}
    coordinator.known_sensor_keys = set(observations.keys())

    entities: list[DMISensor | DMITidewaterSensor | DMILastFetchSensor] = [
        DMILastFetchSensor(
            coordinator=coordinator,
            config_entry=config_entry,
        )
    ]
    for description in sensor_types:
        if description.key in coordinator.known_sensor_keys:
            entities.append(
                DMISensor(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    entity_description=description,
                )
            )

    if coordinator.setup_type == SETUP_TYPE_SEA and coordinator.tidewater_station_id:
        entities.extend(
            DMITidewaterSensor(
                coordinator=coordinator,
                config_entry=config_entry,
                entity_description=description,
            )
            for description in TIDEWATER_SENSOR_TYPES
        )

    async_add_entities(entities, True)

    @callback
    def _async_handle_coordinator_update() -> None:
        """Register newly available parameters as sensor entities."""
        if coordinator.data is None:
            return

        current_params = set(coordinator.data.get("observations", {}).keys())
        new_params = current_params - coordinator.known_sensor_keys
        if not new_params:
            return

        new_entities = [
            DMISensor(
                coordinator=coordinator,
                config_entry=config_entry,
                entity_description=sensor_types_by_key[param_key],
            )
            for param_key in sorted(new_params)
            if param_key in sensor_types_by_key
        ]
        if new_entities:
            coordinator.known_sensor_keys.update(
                entity.entity_description.key for entity in new_entities
            )
            async_add_entities(new_entities, True)

    config_entry.async_on_unload(coordinator.async_add_listener(_async_handle_coordinator_update))


class DMIBaseSensor(CoordinatorEntity[DMIDataUpdateCoordinator], SensorEntity):
    """Shared behavior for DMI sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DMIDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize shared sensor state."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._station_id = str(config_entry.data.get(CONF_STATION_ID) or "")
        self._station_name = str(config_entry.data.get(CONF_STATION_NAME) or "DMI Weather")
        self._setup_type = str(config_entry.data.get(CONF_SETUP_TYPE) or "normal")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            name=self._station_name,
            manufacturer="Danish Meteorological Institute",
            model=(
                f"Composite Weather Station {self._station_id}"
                if self._setup_type == SETUP_TYPE_ADVANCED
                else (
                    f"Sea Level Station {self._station_id}"
                    if self._setup_type == SETUP_TYPE_SEA
                    else f"Weather Station {self._station_id}"
                )
            ),
            configuration_url="https://www.dmi.dk",
        )


class DMISensor(DMIBaseSensor):
    """Representation of a DMI Weather sensor."""

    def __init__(
        self,
        coordinator: DMIDataUpdateCoordinator,
        config_entry: ConfigEntry,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self.entity_description = entity_description

        # Unique ID follows pattern: {entry_id}_{sensor_key}
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"

    @property
    def name(self) -> str | None:
        """Return the sensor name, including backup station suffix when configured."""
        base_name = self.entity_description.name
        if not isinstance(base_name, str):
            return None

        if self._setup_type != SETUP_TYPE_ADVANCED or self.coordinator.data is None:
            return base_name

        observations = self.coordinator.data.get("observations", {})
        param_data = observations.get(self.entity_description.key, {})
        if param_data.get(CONF_SOURCE_TYPE) != SOURCE_TYPE_BACKUP:
            return base_name

        source_station_id = str(param_data.get(CONF_SOURCE_STATION_ID) or "")
        backup = next(
            (
                backup_station
                for backup_station in self._config_entry.data.get(CONF_BACKUP_STATIONS, [])
                if str(backup_station.get(CONF_STATION_ID) or "") == source_station_id
            ),
            None,
        )
        if not backup or not backup.get(CONF_BACKUP_STATION_NAME_SUFFIX, False):
            return base_name

        source_station_name = str(
            backup.get(CONF_STATION_NAME)
            or param_data.get(CONF_SOURCE_STATION_NAME)
            or source_station_id
        )
        return f"{base_name} - {source_station_name}"

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None

        observations = self.coordinator.data.get("observations", {})
        param_data = observations.get(self.entity_description.key, {})

        if param_data:
            return param_data.get("value")

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return {}

        observations = self.coordinator.data.get("observations", {})
        param_data = observations.get(self.entity_description.key, {})

        attributes: dict[str, Any] = {}

        if param_data:
            observed = param_data.get("observed")
            if observed:
                attributes["observation_time"] = observed
            created = param_data.get("created")
            if created:
                attributes["created_time"] = created
            qc_status = param_data.get("qc_status")
            if qc_status:
                attributes["quality_control_status"] = qc_status
            for source_key in (
                CONF_SOURCE_STATION_ID,
                CONF_SOURCE_STATION_NAME,
                CONF_SOURCE_TYPE,
            ):
                source_value = param_data.get(source_key)
                if source_value is not None:
                    attributes[source_key] = source_value

        # Add last updated timestamp
        last_updated = self.coordinator.data.get("last_updated")
        if last_updated:
            attributes["last_updated"] = last_updated.isoformat()

        return attributes


class DMITidewaterSensor(DMIBaseSensor):
    """Representation of an astronomical tide prediction sensor."""

    _PREDICTION_TYPES = {
        "predicted_sea_level": "10minutes",
        "next_high_tide": "maximum",
        "next_low_tide": "minimum",
    }

    def __init__(
        self,
        coordinator: DMIDataUpdateCoordinator,
        config_entry: ConfigEntry,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize a tide prediction sensor."""
        super().__init__(coordinator, config_entry)
        self.entity_description = entity_description
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"

    @property
    def _predictions(self) -> list[dict[str, Any]]:
        """Return the current prediction series."""
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.get("tidewater_forecast") or []

    def _first_prediction(self, prediction_type: str) -> dict[str, Any] | None:
        """Return the first prediction of a given DMI type."""
        return next(
            (
                prediction
                for prediction in self._predictions
                if prediction.get("prediction_type") == prediction_type
            ),
            None,
        )

    @property
    def _current_prediction(self) -> dict[str, Any] | None:
        """Return the prediction represented by this entity."""
        prediction_type = self._PREDICTION_TYPES[self.entity_description.key]
        return self._first_prediction(prediction_type)

    @property
    def native_value(self) -> Any:
        """Return the predicted sea level."""
        prediction = self._current_prediction
        return prediction.get("value") if prediction else None

    @staticmethod
    def _summary(prediction: dict[str, Any] | None) -> dict[str, Any] | None:
        """Return a compact value/timestamp prediction summary."""
        if prediction is None:
            return None
        return {
            "datetime": prediction.get("prediction_time"),
            "value": prediction.get("value"),
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return forecast series, timing, and prediction-station metadata."""
        prediction = self._current_prediction
        attributes: dict[str, Any] = {
            CONF_TIDEWATER_STATION_ID: self._config_entry.data.get(CONF_TIDEWATER_STATION_ID),
            CONF_TIDEWATER_STATION_NAME: self._config_entry.data.get(CONF_TIDEWATER_STATION_NAME),
        }
        if prediction:
            attributes["prediction_time"] = prediction.get("prediction_time")
            attributes["prediction_created_time"] = prediction.get("created")

        low_astronomical_tide = self._config_entry.data.get(CONF_LOW_ASTRONOMICAL_TIDE)
        if low_astronomical_tide is not None:
            attributes[CONF_LOW_ASTRONOMICAL_TIDE] = low_astronomical_tide
        mean_low_water_spring = self._config_entry.data.get(CONF_MEAN_LOW_WATER_SPRING)
        if mean_low_water_spring is not None:
            attributes[CONF_MEAN_LOW_WATER_SPRING] = mean_low_water_spring

        if self.entity_description.key == "predicted_sea_level":
            attributes["forecast"] = [
                {
                    "datetime": item.get("prediction_time"),
                    "value": item.get("value"),
                }
                for item in self._predictions
                if item.get("prediction_type") == "10minutes"
            ]
            attributes["next_high_tide"] = self._summary(self._first_prediction("maximum"))
            attributes["next_low_tide"] = self._summary(self._first_prediction("minimum"))

        if self.coordinator.data is not None:
            last_updated = self.coordinator.data.get("last_updated")
            if isinstance(last_updated, datetime):
                attributes["last_updated"] = last_updated.isoformat()

        return {key: value for key, value in attributes.items() if value is not None}


class DMILastFetchSensor(DMIBaseSensor):
    """Diagnostic sensor for the last successful fetch timestamp."""

    entity_description = LAST_FETCH_SENSOR

    def __init__(
        self,
        coordinator: DMIDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the last-fetch sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_{LAST_FETCH_SENSOR.key}"

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last successful fetch."""
        if self.coordinator.data is None:
            return None

        last_updated = self.coordinator.data.get("last_updated")
        if isinstance(last_updated, datetime):
            return last_updated
        return None
