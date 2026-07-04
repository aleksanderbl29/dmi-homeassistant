"""Data update coordinator for DMI Weather integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CannotConnect,
    DMIApiClient,
    RateLimitExceeded,
    RequestTimeout,
    UpstreamError,
)
from .const import (
    CONF_BACKUP_PARAMETERS,
    CONF_BACKUP_STATIONS,
    CONF_INCLUDE_FORECAST,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SETUP_TYPE,
    CONF_SOURCE_STATION_ID,
    CONF_SOURCE_STATION_NAME,
    CONF_SOURCE_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SETUP_TYPE_ADVANCED,
    SOURCE_TYPE_BACKUP,
    SOURCE_TYPE_PRIMARY,
)

_LOGGER = logging.getLogger(__name__)

# Fixed cooldown applied after a 429, independent of HA's own retry backoff.
RATE_LIMIT_COOLDOWN = timedelta(minutes=1)

# Minimum spacing between the two outbound requests in a single update
# cycle (observations, then forecast), so we never burst two requests
# back-to-back even though they're both well within normal limits.
REQUEST_STAGGER_SECONDS = 2


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
        self.station_id: str = str(config_entry.data.get(CONF_STATION_ID) or "")
        self.station_name: str = str(config_entry.data.get(CONF_STATION_NAME) or "DMI Weather")
        self.setup_type: str = str(config_entry.data.get(CONF_SETUP_TYPE) or "normal")
        self.backup_stations: list[dict[str, Any]] = list(
            config_entry.data.get(CONF_BACKUP_STATIONS, [])
        )

        # Handle coordinates - ensure they're float or None
        lat = config_entry.data.get(CONF_LATITUDE)
        lon = config_entry.data.get(CONF_LONGITUDE)
        self.latitude: float | None = float(lat) if lat is not None else None
        self.longitude: float | None = float(lon) if lon is not None else None

        # Get update interval from options or use default
        update_interval_minutes = config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60
        )
        update_interval = timedelta(minutes=update_interval_minutes)

        # Check if forecast is enabled
        self.include_forecast: bool = config_entry.options.get(CONF_INCLUDE_FORECAST, True)

        # Tracks a cooldown window after a 429, so a single rate-limit hit
        # doesn't turn into a retry storm via HA's own backoff mechanism.
        self._rate_limited_until: datetime | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.station_name})",
            update_interval=update_interval,
            config_entry=config_entry,
        )

    def _return_cached_data(
        self,
        *,
        log_message: str,
        error: Exception,
    ) -> dict[str, Any] | None:
        """Return cached coordinator data when available."""
        if self.data is None:
            return None

        _LOGGER.warning(log_message, self.station_id, error)
        return self.data

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from DMI API.

        Returns:
            Dictionary containing observations, forecast, and last_updated timestamp.

        Raises:
            UpdateFailed: If data fetch fails and no cached data is available.
        """
        now = dt_util.utcnow()

        # If we were rate limited recently, skip hitting DMI again this
        # cycle entirely. Serve cached data instead of raising, so HA
        # doesn't see a failure and doesn't accelerate its retry backoff.
        if self._rate_limited_until and now < self._rate_limited_until:
            _LOGGER.debug(
                "Skipping update for %s, still in rate-limit cooldown until %s",
                self.station_id,
                self._rate_limited_until,
            )
            if self.data is not None:
                return self.data
            raise UpdateFailed("Still in rate-limit cooldown and no cached data yet")

        try:
            async with async_timeout.timeout(30):
                _LOGGER.debug(
                    "Updating DMI data for station %s (forecast enabled=%s, coords=%s,%s)",
                    self.station_id,
                    self.include_forecast,
                    self.latitude,
                    self.longitude,
                )
                # Fetch observations
                primary_observations = await self.api.get_observations(self.station_id)
                observations = self._annotate_observations(
                    primary_observations,
                    station_id=self.station_id,
                    station_name=self.station_name,
                    source_type=SOURCE_TYPE_PRIMARY,
                )

                if self.setup_type == SETUP_TYPE_ADVANCED:
                    await self._async_merge_backup_observations(observations)

                # Fetch forecast if coordinates are available and enabled.
                # Stagger this slightly after the observations call so the
                # two requests in this cycle are never sent back-to-back.
                forecast = None
                if (
                    self.include_forecast
                    and self.latitude is not None
                    and self.longitude is not None
                ):
                    await asyncio.sleep(REQUEST_STAGGER_SECONDS)
                    try:
                        forecast = await self.api.get_forecast(self.latitude, self.longitude)
                        _LOGGER.debug(
                            "Fetched forecast for %s with %d hourly entries",
                            self.station_id,
                            len(forecast.get("hourly", [])) if forecast else 0,
                        )
                    except RateLimitExceeded:
                        # Don't swallow this one -- let the outer handler
                        # set the cooldown so future cycles back off too.
                        raise
                    except Exception as err:
                        _LOGGER.warning("Failed to fetch forecast: %s", err)
                        # Continue without forecast data (non-rate-limit
                        # errors only; e.g. transient connection issue).

                # Success: clear any prior cooldown.
                self._rate_limited_until = None

                return {
                    "observations": observations,
                    "forecast": forecast,
                    "last_updated": now,
                }

        except RateLimitExceeded as err:
            self._rate_limited_until = now + RATE_LIMIT_COOLDOWN
            _LOGGER.warning(
                "DMI rate limit hit for %s, pausing updates until %s",
                self.station_id,
                self._rate_limited_until,
            )
            # If we have prior good data, keep serving it quietly rather
            # than surfacing an error during the cooldown window.
            if self.data is not None:
                return self.data
            raise UpdateFailed(f"Rate limit exceeded, will retry after cooldown: {err}") from err
        except UpstreamError as err:
            cached_data = self._return_cached_data(
                log_message=(
                    "DMI upstream API failure while refreshing %s; "
                    "continuing to serve cached data: %s"
                ),
                error=err,
            )
            if cached_data is not None:
                return cached_data
            raise UpdateFailed(f"Upstream API error: {err}") from err
        except RequestTimeout as err:
            cached_data = self._return_cached_data(
                log_message=(
                    "DMI request timeout while refreshing %s; continuing to serve cached data: %s"
                ),
                error=err,
            )
            if cached_data is not None:
                return cached_data
            raise UpdateFailed(f"Timeout fetching data: {err}") from err
        except CannotConnect as err:
            cached_data = self._return_cached_data(
                log_message=(
                    "Failed to refresh DMI data for %s due to a connection error; "
                    "continuing to serve cached data: %s"
                ),
                error=err,
            )
            if cached_data is not None:
                return cached_data
            raise UpdateFailed(f"Connection error: {err}") from err
        except TimeoutError as err:
            cached_data = self._return_cached_data(
                log_message=(
                    "Timed out refreshing DMI data for %s; continuing to serve cached data: %s"
                ),
                error=err,
            )
            if cached_data is not None:
                return cached_data
            raise UpdateFailed(f"Timeout fetching data: {err}") from err

    def _annotate_observations(
        self,
        observations: dict[str, Any],
        *,
        station_id: str,
        station_name: str,
        source_type: str,
    ) -> dict[str, Any]:
        """Attach source metadata to observations."""
        annotated: dict[str, Any] = {}
        for parameter_id, observation in observations.items():
            annotated[parameter_id] = {
                **observation,
                CONF_SOURCE_STATION_ID: station_id,
                CONF_SOURCE_STATION_NAME: station_name,
                CONF_SOURCE_TYPE: source_type,
            }
        return annotated

    async def _async_merge_backup_observations(self, observations: dict[str, Any]) -> None:
        """Merge selected observations from backup stations into the primary data."""
        for backup in self.backup_stations:
            backup_station_id = str(backup.get(CONF_STATION_ID) or "")
            backup_station_name = str(backup.get(CONF_STATION_NAME) or backup_station_id)
            selected_parameters = {
                str(parameter_id)
                for parameter_id in backup.get(CONF_BACKUP_PARAMETERS, [])
                if parameter_id
            }
            if not backup_station_id or not selected_parameters:
                continue

            try:
                backup_observations = self._annotate_observations(
                    await self.api.get_observations(backup_station_id),
                    station_id=backup_station_id,
                    station_name=backup_station_name,
                    source_type=SOURCE_TYPE_BACKUP,
                )
            except RateLimitExceeded:
                # Preserve the coordinator-wide rate-limit cooldown behavior.
                raise
            except (CannotConnect, RequestTimeout, UpstreamError, TimeoutError) as err:
                _LOGGER.warning(
                    "Failed to fetch backup observations for station %s; skipping backup: %s",
                    backup_station_id,
                    err,
                )
                continue

            for parameter_id in selected_parameters:
                backup_value = backup_observations.get(parameter_id)
                if backup_value is None:
                    continue
                if parameter_id not in observations:
                    observations[parameter_id] = backup_value
