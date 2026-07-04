"""Config flow for DMI Weather integration."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from typing import Any

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
    CONF_BACKUP_PARAMETERS,
    CONF_BACKUP_STATION_NAME_SUFFIX,
    CONF_BACKUP_STATIONS,
    CONF_INCLUDE_FORECAST,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SETUP_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_USE_COORDINATES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SENSOR_TYPES_BY_KEY,
    SETUP_TYPE_ADVANCED,
    SETUP_TYPE_NORMAL,
)

_LOGGER = logging.getLogger(__name__)


class DMIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DMI Weather."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._stations: list[dict[str, Any]] = []
        self._advanced_primary: dict[str, Any] | None = None
        self._advanced_backup_count = 1
        self._advanced_backups: list[dict[str, Any]] = []
        self._advanced_current_backup_index = 0

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["station", "advanced_primary"],
        )

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle normal station selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station = self._get_station_by_id(str(user_input.get(CONF_STATION_ID, "")))
            if station is None:
                errors["base"] = "invalid_station"
            else:
                data = self._build_primary_entry_data(station, user_input, SETUP_TYPE_NORMAL)
                await self.async_set_unique_id(f"dmi_{data[CONF_STATION_ID]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_STATION_NAME], data=data)

        if not await self._async_load_stations():
            return self.async_show_form(
                step_id="station",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
            )

        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=self._build_station_options(),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_USE_COORDINATES, default=False): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_advanced_primary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the primary station for the advanced flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station = self._get_station_by_id(str(user_input.get(CONF_STATION_ID, "")))
            if station is None:
                errors["base"] = "invalid_station"
            else:
                self._advanced_primary = self._build_primary_entry_data(
                    station,
                    user_input,
                    SETUP_TYPE_ADVANCED,
                )
                self._advanced_backups = []
                self._advanced_backup_count = 1
                self._advanced_current_backup_index = 0
                return await self.async_step_advanced_backup_count()

        if not await self._async_load_stations():
            return self.async_show_form(
                step_id="advanced_primary",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
            )

        return self.async_show_form(
            step_id="advanced_primary",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=self._build_station_options(),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_USE_COORDINATES, default=False): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_advanced_backup_count(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how many backup stations to configure."""
        if user_input is not None:
            self._advanced_backup_count = int(user_input["backup_station_count"])
            self._advanced_backups = []
            self._advanced_current_backup_index = 0
            return await self.async_step_advanced_backup_station()

        return self.async_show_form(
            step_id="advanced_backup_count",
            data_schema=vol.Schema(
                {
                    vol.Required("backup_station_count", default="1"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": "1", "label": "1"},
                                {"value": "2", "label": "2"},
                                {"value": "3", "label": "3"},
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_advanced_backup_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a backup station."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = str(user_input.get(CONF_STATION_ID, ""))
            station = self._get_station_by_id(station_id)
            primary_station_id = str(self._advanced_primary[CONF_STATION_ID])
            selected_backup_ids = {
                str(backup[CONF_STATION_ID]) for backup in self._advanced_backups
            }

            if station is None:
                errors["base"] = "invalid_station"
            elif station_id == primary_station_id:
                errors["base"] = "backup_matches_primary"
            elif station_id in selected_backup_ids:
                errors["base"] = "duplicate_backup_station"
            else:
                backup_parameters = self._get_backup_parameter_ids(station)
                if not backup_parameters:
                    errors["base"] = "no_backup_parameters"
                else:
                    self._advanced_backups.append(
                        {
                            CONF_STATION_ID: station_id,
                            CONF_STATION_NAME: station.get(CONF_STATION_NAME)
                            or station.get("name"),
                            CONF_LATITUDE: station.get(CONF_LATITUDE) or station.get("latitude"),
                            CONF_LONGITUDE: station.get(CONF_LONGITUDE) or station.get("longitude"),
                            CONF_BACKUP_PARAMETERS: backup_parameters,
                            CONF_BACKUP_STATION_NAME_SUFFIX: bool(
                                user_input.get(CONF_BACKUP_STATION_NAME_SUFFIX, False)
                            ),
                        }
                    )
                    self._advanced_current_backup_index += 1
                    if self._advanced_current_backup_index >= self._advanced_backup_count:
                        return await self._async_create_advanced_entry()
                    return await self.async_step_advanced_backup_station()

        return self.async_show_form(
            step_id="advanced_backup_station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=self._build_station_options(),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_BACKUP_STATION_NAME_SUFFIX,
                        default=False,
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders={"backup_index": str(self._advanced_current_backup_index + 1)},
        )

    async def _async_create_advanced_entry(self) -> ConfigFlowResult:
        """Create an advanced composite entry."""
        if self._advanced_primary is None:
            return await self.async_step_user()

        entry_data = {
            **self._advanced_primary,
            CONF_BACKUP_STATIONS: self._advanced_backups,
        }

        hash_payload = {
            CONF_STATION_ID: entry_data[CONF_STATION_ID],
            CONF_USE_COORDINATES: entry_data[CONF_USE_COORDINATES],
            CONF_BACKUP_STATIONS: [
                {
                    CONF_STATION_ID: backup[CONF_STATION_ID],
                    CONF_BACKUP_PARAMETERS: sorted(backup[CONF_BACKUP_PARAMETERS]),
                    CONF_BACKUP_STATION_NAME_SUFFIX: backup[CONF_BACKUP_STATION_NAME_SUFFIX],
                }
                for backup in self._advanced_backups
            ],
        }
        hash_digest = hashlib.sha1(
            json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:12]

        await self.async_set_unique_id(f"dmi_advanced_{entry_data[CONF_STATION_ID]}_{hash_digest}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"{entry_data[CONF_STATION_NAME]} + backups",
            data=entry_data,
        )

    def _build_primary_entry_data(
        self,
        station: Mapping[str, Any],
        user_input: Mapping[str, Any],
        setup_type: str,
    ) -> dict[str, Any]:
        """Build the stored entry data for a primary station."""
        latitude = station.get("latitude")
        longitude = station.get("longitude")
        use_coordinates = bool(user_input.get(CONF_USE_COORDINATES, False))
        if use_coordinates:
            latitude = self.hass.config.latitude
            longitude = self.hass.config.longitude

        return {
            CONF_SETUP_TYPE: setup_type,
            CONF_STATION_ID: str(station.get("stationId") or ""),
            CONF_STATION_NAME: str(station.get("name") or "DMI Weather"),
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
            CONF_USE_COORDINATES: use_coordinates,
        }

    def _get_station_by_id(self, station_id: str) -> dict[str, Any] | None:
        """Return a station by id."""
        for station in self._stations:
            if str(station.get("stationId", "")) == station_id:
                return station
        return None

    def _build_station_options(self) -> list[dict[str, str]]:
        """Build selector options for stations."""
        station_options_by_id: dict[str, dict[str, str]] = {}
        for station in self._stations:
            station_id = station.get("stationId")
            if not station_id:
                continue
            name = station.get("name") or f"Station {station_id}"
            station_options_by_id[str(station_id)] = {
                "value": str(station_id),
                "label": f"{name} ({station_id})",
            }

        station_options = list(station_options_by_id.values())
        station_options.sort(key=lambda option: option["label"])
        return station_options

    def _get_backup_parameter_ids(self, backup_station: Mapping[str, Any]) -> list[str]:
        """Return supported backup parameters missing from the primary station."""
        primary_station = self._get_station_by_id(str(self._advanced_primary[CONF_STATION_ID]))
        primary_parameters = {
            parameter_id
            for parameter_id in primary_station.get("parameterId", [])
            if parameter_id in SENSOR_TYPES_BY_KEY
        }
        backup_parameters = [
            parameter_id
            for parameter_id in backup_station.get("parameterId", [])
            if parameter_id in SENSOR_TYPES_BY_KEY and parameter_id not in primary_parameters
        ]

        return sorted(
            backup_parameters,
            key=lambda parameter_id: SENSOR_TYPES_BY_KEY[parameter_id].name or parameter_id,
        )

    async def _async_load_stations(self) -> bool:
        """Load station list from the DMI API."""
        if self._stations:
            return True

        try:
            session = async_get_clientsession(self.hass)
            api_client = DMIApiClient(session)
            self._stations = await api_client.get_stations(active_only=True)
            _LOGGER.debug("Fetched %d stations from DMI API", len(self._stations))
        except CannotConnect as err:
            _LOGGER.error("Cannot connect to DMI API: %s", err)
            return False
        except Exception as err:  # pragma: no cover - defensive path
            _LOGGER.exception("Unexpected error fetching stations: %s", err)
            return False

        return bool(self._stations)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return DMIOptionsFlowHandler()


class DMIOptionsFlowHandler(OptionsFlow):
    """Handle options flow for DMI Weather."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60
        )
        current_include_forecast = self.config_entry.options.get(CONF_INCLUDE_FORECAST, True)

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
