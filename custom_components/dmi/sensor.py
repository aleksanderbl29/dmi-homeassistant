"""Sensor platform for DMI Weather integration."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_BACKUP_STATION_NAME_SUFFIX,
    CONF_BACKUP_STATIONS,
    CONF_SETUP_TYPE,
    CONF_SOURCE_STATION_ID,
    CONF_SOURCE_STATION_NAME,
    CONF_SOURCE_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
    LAST_FETCH_SENSOR,
    SENSOR_TYPES,
    SETUP_TYPE_ADVANCED,
    SOURCE_TYPE_BACKUP,
)
from .coordinator import DMIDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DMI Weather sensor entities from config entry."""
    coordinator: DMIDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Get the available parameters from the current observations
    observations = coordinator.data.get("observations", {}) if coordinator.data else {}
    available_params = set(observations.keys())

    # Create sensors only for parameters the station actually reports
    entities: list[DMISensor | DMILastFetchSensor] = [
        DMILastFetchSensor(
            coordinator=coordinator,
            config_entry=config_entry,
        )
    ]
    for description in SENSOR_TYPES:
        # Only create sensor if station has this parameter
        if description.key in available_params:
            entities.append(
                DMISensor(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    entity_description=description,
                )
            )

    async_add_entities(entities, True)


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
                else f"Weather Station {self._station_id}"
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
        self.entity_description = self._description_with_source_suffix(entity_description)

        # Unique ID follows pattern: {entry_id}_{sensor_key}
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"

    def _description_with_source_suffix(
        self,
        entity_description: SensorEntityDescription,
    ) -> SensorEntityDescription:
        """Append backup station name to backup-sourced sensor names when requested."""
        if self._setup_type != SETUP_TYPE_ADVANCED or self.coordinator.data is None:
            return entity_description

        observations = self.coordinator.data.get("observations", {})
        param_data = observations.get(entity_description.key, {})
        if param_data.get(CONF_SOURCE_TYPE) != SOURCE_TYPE_BACKUP:
            return entity_description

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
            return entity_description

        source_station_name = str(
            backup.get(CONF_STATION_NAME)
            or param_data.get(CONF_SOURCE_STATION_NAME)
            or source_station_id
        )
        return replace(
            entity_description,
            name=f"{entity_description.name} {source_station_name}",
        )

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
