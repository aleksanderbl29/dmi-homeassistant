"""Data update coordinator for DMI Weather integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
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
    CONF_HAS_SEA_OBSERVATIONS,
    CONF_INCLUDE_FORECAST,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SEA_OBSERVATION_STATION_ID,
    CONF_SEA_OBSERVATION_STATION_NAME,
    CONF_SETUP_TYPE,
    CONF_SOURCE_STATION_ID,
    CONF_SOURCE_STATION_NAME,
    CONF_SOURCE_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_TIDEWATER_STATION_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SETUP_TYPE_ADVANCED,
    SETUP_TYPE_SEA,
    SOURCE_TYPE_BACKUP,
    SOURCE_TYPE_PRIMARY,
)

_LOGGER = logging.getLogger(__name__)

# Fixed cooldown applied after a 429, independent of HA's own retry backoff.
RATE_LIMIT_COOLDOWN = timedelta(minutes=1)
MAX_RATE_LIMIT_COOLDOWN = timedelta(hours=1)

# Keep this outside the config-entry coordinator map so it survives failed
# setup attempts and is shared by every DMI entry in the Home Assistant
# instance. DMI applies fair-use limits across requests, not per coordinator.
RATE_LIMIT_STATE_KEY = f"{DOMAIN}_api_state"

# Minimum spacing between the two outbound requests in a single update
# cycle (observations, then forecast), so we never burst two requests
# back-to-back even though they're both well within normal limits.
REQUEST_STAGGER_SECONDS = 2
TIDEWATER_FORECAST_HOURS = 24
DKSS_FORECAST_HOURS = 120
TIDEWATER_FORECAST_REFRESH_INTERVAL = timedelta(hours=6)
DKSS_FORECAST_REFRESH_INTERVAL = timedelta(hours=3)
WEATHER_FORECAST_REFRESH_INTERVAL = timedelta(hours=3)
WEATHER_FORECAST_RETRY_INTERVAL = timedelta(minutes=1)


@dataclass
class _SharedApiState:
    """Rate-limit and concurrency state shared by all DMI config entries."""

    update_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    rate_limited_until: datetime | None = None
    consecutive_rate_limits: int = 0


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
        self.has_sea_observations: bool = bool(
            config_entry.data.get(CONF_HAS_SEA_OBSERVATIONS, True)
        )
        self.sea_observation_station_id: str = str(
            config_entry.data.get(CONF_SEA_OBSERVATION_STATION_ID) or ""
        )
        self.sea_observation_station_name: str = str(
            config_entry.data.get(CONF_SEA_OBSERVATION_STATION_NAME)
            or self.sea_observation_station_id
        )
        self.tidewater_station_id: str = str(config_entry.data.get(CONF_TIDEWATER_STATION_ID) or "")
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
        self.include_forecast: bool = (
            self.setup_type != SETUP_TYPE_SEA
            and config_entry.options.get(CONF_INCLUDE_FORECAST, True)
        )

        # The state must outlive this coordinator because Home Assistant
        # recreates coordinators when an initial config-entry setup is retried.
        self._api_state: _SharedApiState = hass.data.setdefault(
            RATE_LIMIT_STATE_KEY, _SharedApiState()
        )

        # Forecast products change much less frequently than observations.
        # Cache them independently so ten-minute sea observations do not
        # repeatedly request the same forecast data.
        self._tidewater_forecast: list[dict[str, Any]] | None = None
        self._tidewater_forecast_attempted_at: datetime | None = None
        self._dkss_forecast: dict[str, Any] | None = None
        self._dkss_forecast_attempted_at: datetime | None = None
        self._weather_forecast: dict[str, Any] | None = None
        self._weather_forecast_attempted_at: datetime | None = None
        self._weather_forecast_retry_at: datetime | None = None
        self._weather_forecast_rate_limits: int = 0
        self._weather_forecast_retry_unsub: Callable[[], None] | None = None

        # Sensor platform tracks which observation keys already have entities.
        self.known_sensor_keys: set[str] = set()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.station_name})",
            update_interval=update_interval,
            config_entry=config_entry,
        )

    async def async_shutdown(self) -> None:
        """Cancel pending forecast retries before shutting down the coordinator."""
        self._cancel_weather_forecast_retry()
        await super().async_shutdown()

    @callback
    def _cancel_weather_forecast_retry(self) -> None:
        """Cancel the pending forecast retry timer, if present."""
        if self._weather_forecast_retry_unsub is not None:
            self._weather_forecast_retry_unsub()
            self._weather_forecast_retry_unsub = None

    @callback
    def _schedule_weather_forecast_retry(self, retry_at: datetime) -> None:
        """Schedule a forecast request when a failed forecast can be retried."""
        self._cancel_weather_forecast_retry()
        self._weather_forecast_retry_unsub = async_track_point_in_utc_time(
            self.hass,
            self._async_retry_weather_forecast,
            retry_at,
        )

    async def _async_retry_weather_forecast(self, _: datetime) -> None:
        """Retry only the failed forecast when its deadline arrives."""
        self._weather_forecast_retry_unsub = None
        if self.hass.is_stopping or self.latitude is None or self.longitude is None:
            return

        async with self._api_state.update_lock:
            now = dt_util.utcnow()
            if self._weather_forecast_retry_at is None or now < self._weather_forecast_retry_at:
                return

            try:
                async with asyncio.timeout(60):
                    self._weather_forecast_attempted_at = now
                    self._weather_forecast = await self.api.get_forecast(
                        self.latitude,
                        self.longitude,
                    )
            except (
                CannotConnect,
                RateLimitExceeded,
                RequestTimeout,
                UpstreamError,
                TimeoutError,
            ) as err:
                self._record_weather_forecast_failure(err)
                return

            self._weather_forecast_retry_at = None
            self._weather_forecast_rate_limits = 0
            if self.data is not None:
                self.data = {
                    **self.data,
                    "forecast": self._current_weather_forecast(now),
                }
                self.async_update_listeners()

    def _record_weather_forecast_failure(self, err: Exception) -> None:
        """Schedule a forecast retry, backing off when DMI returns HTTP 429."""
        if isinstance(err, RateLimitExceeded):
            self._weather_forecast_rate_limits += 1
            multiplier = 2 ** (self._weather_forecast_rate_limits - 1)
            delay = min(
                WEATHER_FORECAST_RETRY_INTERVAL * multiplier,
                MAX_RATE_LIMIT_COOLDOWN,
            )
        else:
            self._weather_forecast_rate_limits = 0
            delay = WEATHER_FORECAST_RETRY_INTERVAL

        self._weather_forecast_retry_at = dt_util.utcnow() + delay
        if isinstance(err, RateLimitExceeded) and err.retry_at is not None:
            self._weather_forecast_retry_at = max(self._weather_forecast_retry_at, err.retry_at)
        self._schedule_weather_forecast_retry(self._weather_forecast_retry_at)
        _LOGGER.warning(
            "Failed to refresh weather forecast for %s; retrying at %s; "
            "continuing with cached forecast: %s",
            self.station_id,
            self._weather_forecast_retry_at,
            err,
        )

    @property
    def _rate_limited_until(self) -> datetime | None:
        """Return the shared rate-limit deadline."""
        return self._api_state.rate_limited_until

    @_rate_limited_until.setter
    def _rate_limited_until(self, value: datetime | None) -> None:
        """Set the shared rate-limit deadline."""
        self._api_state.rate_limited_until = value

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

    @staticmethod
    def _empty_data() -> dict[str, Any]:
        """Return an unavailable payload that allows setup to complete."""
        return {
            "observations": {},
            "forecast": None,
            "tidewater_forecast": None,
            "dkss_forecast": None,
            "last_updated": None,
        }

    @staticmethod
    def _forecast_refresh_due(
        attempted_at: datetime | None,
        now: datetime,
        interval: timedelta,
    ) -> bool:
        """Return whether a forecast should be requested again."""
        return attempted_at is None or now - attempted_at >= interval

    @staticmethod
    def _future_forecast_items(
        items: list[dict[str, Any]],
        timestamp_key: str,
        now: datetime,
    ) -> list[dict[str, Any]]:
        """Remove expired items from cached forecast output."""
        future_items = []
        for item in items:
            timestamp = item.get(timestamp_key)
            parsed_timestamp = (
                dt_util.parse_datetime(timestamp) if isinstance(timestamp, str) else None
            )
            if parsed_timestamp is not None and parsed_timestamp >= now:
                future_items.append(item)
        return future_items

    def _current_tidewater_forecast(
        self,
        now: datetime,
    ) -> list[dict[str, Any]] | None:
        """Return unexpired astronomical tide predictions."""
        if self._tidewater_forecast is None:
            return None
        return self._future_forecast_items(
            self._tidewater_forecast,
            "prediction_time",
            now,
        )

    def _current_dkss_forecast(self, now: datetime) -> dict[str, Any] | None:
        """Return DKSS metadata with unexpired forecast values."""
        if self._dkss_forecast is None:
            return None
        return {
            **self._dkss_forecast,
            "forecast": self._future_forecast_items(
                self._dkss_forecast.get("forecast", []),
                "datetime",
                now,
            ),
        }

    def _current_weather_forecast(self, now: datetime) -> dict[str, Any] | None:
        """Return weather forecast metadata with unexpired hourly values."""
        if self._weather_forecast is None:
            return None
        return {
            **self._weather_forecast,
            "hourly": self._future_forecast_items(
                self._weather_forecast.get("hourly", []),
                "datetime",
                now,
            ),
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from DMI API.

        Returns:
            Dictionary containing observations, forecast, and last_updated timestamp.

        Raises:
            UpdateFailed: If data fetch fails and no cached data is available.
        """
        # Multiple entries (and overlapping manual refreshes) otherwise burst
        # requests at DMI together. Recheck the shared cooldown only after
        # acquiring the lock because another entry may have just received 429.
        async with self._api_state.update_lock:
            return await self._async_update_data_locked()

    async def _async_update_data_locked(self) -> dict[str, Any]:
        """Fetch data while holding the shared DMI update lock."""
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
            return self._empty_data()

        try:
            async with asyncio.timeout(60):
                _LOGGER.debug(
                    "Updating DMI data for station %s (forecast enabled=%s, coords=%s,%s)",
                    self.station_id,
                    self.include_forecast,
                    self.latitude,
                    self.longitude,
                )
                # Fetch observations from the configured DMI dataset.
                if self.setup_type == SETUP_TYPE_SEA:
                    observation_station_id = self.sea_observation_station_id or (
                        self.station_id if self.has_sea_observations else ""
                    )
                    observation_station_name = self.sea_observation_station_name or (
                        self.station_name if observation_station_id == self.station_id else ""
                    )
                    primary_observations = (
                        await self.api.get_sea_observations(observation_station_id)
                        if observation_station_id
                        else {}
                    )
                else:
                    observation_station_id = self.station_id
                    observation_station_name = self.station_name
                    primary_observations = await self.api.get_observations(self.station_id)
                observations = self._annotate_observations(
                    primary_observations,
                    station_id=observation_station_id,
                    station_name=observation_station_name,
                    source_type=(
                        SOURCE_TYPE_PRIMARY
                        if observation_station_id == self.station_id
                        else SOURCE_TYPE_BACKUP
                    ),
                )

                if self.setup_type == SETUP_TYPE_ADVANCED:
                    await self._async_merge_backup_observations(observations)

                if (
                    self.setup_type == SETUP_TYPE_SEA
                    and self.tidewater_station_id
                    and self._forecast_refresh_due(
                        self._tidewater_forecast_attempted_at,
                        now,
                        TIDEWATER_FORECAST_REFRESH_INTERVAL,
                    )
                ):
                    await asyncio.sleep(REQUEST_STAGGER_SECONDS)
                    self._tidewater_forecast_attempted_at = now
                    try:
                        self._tidewater_forecast = await self.api.get_tidewater_forecast(
                            self.tidewater_station_id,
                            now,
                            now + timedelta(hours=TIDEWATER_FORECAST_HOURS),
                        )
                    except (
                        CannotConnect,
                        RateLimitExceeded,
                        RequestTimeout,
                        UpstreamError,
                        TimeoutError,
                    ) as err:
                        _LOGGER.warning(
                            "Failed to refresh tide predictions for station %s; "
                            "continuing with cached predictions: %s",
                            self.tidewater_station_id,
                            err,
                        )
                tidewater_forecast = self._current_tidewater_forecast(now)

                if (
                    self.setup_type == SETUP_TYPE_SEA
                    and self.latitude is not None
                    and self.longitude is not None
                    and self._forecast_refresh_due(
                        self._dkss_forecast_attempted_at,
                        now,
                        DKSS_FORECAST_REFRESH_INTERVAL,
                    )
                ):
                    await asyncio.sleep(REQUEST_STAGGER_SECONDS)
                    self._dkss_forecast_attempted_at = now
                    try:
                        self._dkss_forecast = await self.api.get_dkss_forecast(
                            self.latitude,
                            self.longitude,
                            now,
                            now + timedelta(hours=DKSS_FORECAST_HOURS),
                        )
                    except (
                        CannotConnect,
                        RateLimitExceeded,
                        RequestTimeout,
                        UpstreamError,
                        TimeoutError,
                    ) as err:
                        _LOGGER.warning(
                            "Failed to refresh DKSS forecast at %s,%s; "
                            "continuing with cached forecast: %s",
                            self.latitude,
                            self.longitude,
                            err,
                        )
                dkss_forecast = self._current_dkss_forecast(now)

                # Fetch forecast if coordinates are available and enabled.
                # Stagger this slightly after the observations call so the
                # two requests in this cycle are never sent back-to-back.
                if (
                    self.setup_type != SETUP_TYPE_SEA
                    and self.include_forecast
                    and self.latitude is not None
                    and self.longitude is not None
                    and (
                        now >= self._weather_forecast_retry_at
                        if self._weather_forecast_retry_at is not None
                        else self._forecast_refresh_due(
                            self._weather_forecast_attempted_at,
                            now,
                            WEATHER_FORECAST_REFRESH_INTERVAL,
                        )
                    )
                ):
                    await asyncio.sleep(REQUEST_STAGGER_SECONDS)
                    self._weather_forecast_attempted_at = now
                    try:
                        self._weather_forecast = await self.api.get_forecast(
                            self.latitude,
                            self.longitude,
                        )
                        self._weather_forecast_retry_at = None
                        self._weather_forecast_rate_limits = 0
                        self._cancel_weather_forecast_retry()
                        _LOGGER.debug(
                            "Fetched forecast for %s with %d hourly entries",
                            self.station_id,
                            len(self._weather_forecast.get("hourly", [])),
                        )
                    except (
                        CannotConnect,
                        RateLimitExceeded,
                        RequestTimeout,
                        UpstreamError,
                        TimeoutError,
                    ) as err:
                        self._record_weather_forecast_failure(err)
                forecast = self._current_weather_forecast(now)

                # Success: clear the shared cooldown and its exponential
                # backoff, since DMI is accepting requests again.
                self._rate_limited_until = None
                self._api_state.consecutive_rate_limits = 0

                return {
                    "observations": observations,
                    "forecast": forecast,
                    "tidewater_forecast": tidewater_forecast,
                    "dkss_forecast": dkss_forecast,
                    "last_updated": now,
                }

        except RateLimitExceeded as err:
            self._api_state.consecutive_rate_limits += 1
            multiplier = 2 ** (self._api_state.consecutive_rate_limits - 1)
            cooldown = min(
                RATE_LIMIT_COOLDOWN * multiplier,
                MAX_RATE_LIMIT_COOLDOWN,
            )
            self._rate_limited_until = dt_util.utcnow() + cooldown
            if err.retry_at is not None:
                self._rate_limited_until = max(self._rate_limited_until, err.retry_at)
            _LOGGER.warning(
                "DMI rate limit hit for %s, pausing all DMI updates for %s until %s",
                self.station_id,
                cooldown,
                self._rate_limited_until,
            )
            # If we have prior good data, keep serving it quietly rather
            # than surfacing an error during the cooldown window.
            if self.data is not None:
                return self.data
            _LOGGER.warning(
                "Loading entry %s without initial data; DMI will be retried "
                "on the next scheduled update",
                self.station_id,
            )
            return self._empty_data()
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

            await asyncio.sleep(REQUEST_STAGGER_SECONDS)

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
