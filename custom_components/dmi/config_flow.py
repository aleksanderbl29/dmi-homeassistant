"""Config flow for DMI Weather integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import CannotConnect, DMIApiClient
from .const import (
    CONF_INCLUDE_FORECAST,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_USE_COORDINATES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class DMIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DMI Weather."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._stations: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        return await self.async_step_station(user_input)

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle station selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = user_input.get(CONF_STATION_ID)
            use_coordinates = user_input.get(CONF_USE_COORDINATES, False)

            # Find station info
            station_name = "DMI Weather"
            latitude = None
            longitude = None

            for station in self._stations:
                if station["stationId"] == station_id:
                    station_name = station["name"] or f"Station {station_id}"
                    latitude = station.get("latitude")
                    longitude = station.get("longitude")
                    break

            # If using HA coordinates, override station coordinates
            if use_coordinates:
                latitude = self.hass.config.latitude
                longitude = self.hass.config.longitude

            # Set unique ID and check if already configured
            await self.async_set_unique_id(f"dmi_{station_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=station_name,
                data={
                    CONF_STATION_ID: station_id,
                    CONF_STATION_NAME: station_name,
                    CONF_LATITUDE: latitude,
                    CONF_LONGITUDE: longitude,
                    CONF_USE_COORDINATES: use_coordinates,
                },
            )

        # Fetch stations list
        try:
            session = async_get_clientsession(self.hass)
            api_client = DMIApiClient(session)
            self._stations = await api_client.get_stations(active_only=True)
        except CannotConnect:
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="station",
                data_schema=vol.Schema({}),
                errors=errors,
            )
        except Exception:
            _LOGGER.exception("Unexpected error fetching stations")
            errors["base"] = "unknown"
            return self.async_show_form(
                step_id="station",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Build station options for selector
        station_options = [
            {
                "value": station["stationId"],
                "label": f"{station['name']} ({station['stationId']})"
                if station["name"]
                else station["stationId"],
            }
            for station in self._stations
            if station["stationId"]
        ]

        # Sort by label
        station_options.sort(key=lambda x: x["label"])

        data_schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=station_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_USE_COORDINATES, default=False): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="station",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return DMIOptionsFlowHandler(config_entry)


class DMIOptionsFlowHandler(OptionsFlow):
    """Handle options flow for DMI Weather."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values or defaults
        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60
        )
        current_include_forecast = self.config_entry.options.get(
            CONF_INCLUDE_FORECAST, True
        )

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=current_interval,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=10,
                        max=60,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="minutes",
                    )
                ),
                vol.Optional(
                    CONF_INCLUDE_FORECAST,
                    default=current_include_forecast,
                ): BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema)

