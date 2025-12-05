"""Data update coordinator for DMI Weather integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import CannotConnect, DMIApiClient, RateLimitExceeded
from .const import (
    CONF_INCLUDE_FORECAST,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class DMIDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for fetching DMI weather data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_client: DMIApiClient,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            config_entry: Config entry for this integration.
            api_client: DMI API client instance.
        """
        self.api = api_client
        self.station_id: str = config_entry.data.get(CONF_STATION_ID, "")
        self.station_name: str = config_entry.data.get(CONF_STATION_NAME, "DMI Weather")
        self.latitude: float | None = config_entry.data.get(CONF_LATITUDE)
        self.longitude: float | None = config_entry.data.get(CONF_LONGITUDE)

        # Get update interval from options or use default
        update_interval_minutes = config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60
        )
        update_interval = timedelta(minutes=update_interval_minutes)

        # Check if forecast is enabled
        self.include_forecast: bool = config_entry.options.get(
            CONF_INCLUDE_FORECAST, True
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.station_name})",
            update_interval=update_interval,
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from DMI API.

        Returns:
            Dictionary containing observations, forecast, and last_updated timestamp.

        Raises:
            UpdateFailed: If data fetch fails.
        """
        try:
            async with async_timeout.timeout(30):
                # Fetch observations
                observations = await self.api.get_observations(self.station_id)

                # Fetch forecast if coordinates are available and enabled
                forecast = None
                if (
                    self.include_forecast
                    and self.latitude is not None
                    and self.longitude is not None
                ):
                    try:
                        forecast = await self.api.get_forecast(
                            self.latitude, self.longitude
                        )
                    except Exception as err:
                        _LOGGER.warning("Failed to fetch forecast: %s", err)
                        # Continue without forecast data

                return {
                    "observations": observations,
                    "forecast": forecast,
                    "last_updated": dt_util.utcnow(),
                }

        except RateLimitExceeded as err:
            raise UpdateFailed(
                f"Rate limit exceeded, will retry: {err}"
            ) from err
        except CannotConnect as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching data: {err}") from err

