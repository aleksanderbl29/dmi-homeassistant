"""Sensor platform for DMI Weather integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, CONF_STATION_NAME, DOMAIN, SENSOR_TYPES
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
    entities: list[DMISensor] = []
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


class DMISensor(CoordinatorEntity[DMIDataUpdateCoordinator], SensorEntity):
    """Representation of a DMI Weather sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DMIDataUpdateCoordinator,
        config_entry: ConfigEntry,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self.entity_description = entity_description
        self._config_entry = config_entry
        self._station_id = config_entry.data.get(CONF_STATION_ID, "")
        self._station_name = config_entry.data.get(CONF_STATION_NAME, "DMI Weather")

        # Unique ID follows pattern: {entry_id}_{sensor_key}
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            name=self._station_name,
            manufacturer="Danish Meteorological Institute",
            model=f"Weather Station {self._station_id}",
            configuration_url="https://www.dmi.dk",
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

        # Add last updated timestamp
        last_updated = self.coordinator.data.get("last_updated")
        if last_updated:
            attributes["last_updated"] = last_updated.isoformat()

        return attributes

