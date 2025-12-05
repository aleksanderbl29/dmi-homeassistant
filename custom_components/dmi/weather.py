"""Weather platform for DMI Weather integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONDITION_MAP, CONF_STATION_ID, CONF_STATION_NAME, DOMAIN
from .coordinator import DMIDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DMI Weather weather entity from config entry."""
    coordinator: DMIDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities([DMIWeather(coordinator, config_entry)], True)


class DMIWeather(CoordinatorEntity[DMIDataUpdateCoordinator], WeatherEntity):
    """Representation of DMI Weather."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_visibility_unit = "km"
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY

    def __init__(
        self,
        coordinator: DMIDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)

        self._config_entry = config_entry
        self._station_id = config_entry.data.get(CONF_STATION_ID, "")
        self._station_name = config_entry.data.get(CONF_STATION_NAME, "DMI Weather")

        self._attr_unique_id = f"{config_entry.entry_id}_weather"

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
    def _observations(self) -> dict[str, Any]:
        """Get current observations from coordinator data."""
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.get("observations", {})

    def _get_observation_value(self, key: str) -> Any:
        """Get a specific observation value."""
        obs = self._observations.get(key, {})
        return obs.get("value") if obs else None

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        # Try to get weather code from observations
        weather_code = self._get_observation_value("weather")

        if weather_code is not None:
            try:
                code = int(weather_code)
                return CONDITION_MAP.get(code, "cloudy")
            except (ValueError, TypeError):
                pass

        # Default based on cloud cover if no weather code
        cloud_cover = self._get_observation_value("cloud_cover")
        if cloud_cover is not None:
            try:
                cover = float(cloud_cover)
                if cover < 20:
                    return "sunny"
                elif cover < 60:
                    return "partlycloudy"
                else:
                    return "cloudy"
            except (ValueError, TypeError):
                pass

        return "cloudy"

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        return self._get_observation_value("temp_dry")

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        return self._get_observation_value("humidity")

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        return self._get_observation_value("pressure_at_sea")

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        return self._get_observation_value("wind_speed")

    @property
    def wind_bearing(self) -> float | None:
        """Return the wind bearing."""
        return self._get_observation_value("wind_dir")

    @property
    def native_visibility(self) -> float | None:
        """Return the visibility in kilometers."""
        visibility_m = self._get_observation_value("visibility")
        if visibility_m is not None:
            try:
                # Convert from meters to kilometers
                return float(visibility_m) / 1000
            except (ValueError, TypeError):
                pass
        return None

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast."""
        if self.coordinator.data is None:
            return None

        forecast_data = self.coordinator.data.get("forecast")
        if forecast_data is None:
            return None

        hourly = forecast_data.get("hourly", [])
        if not hourly:
            return None

        forecasts: list[Forecast] = []
        for entry in hourly:
            forecast = Forecast(
                datetime=entry.get("datetime"),
            )

            if "temperature" in entry:
                forecast["native_temperature"] = entry["temperature"]

            if "wind_speed" in entry:
                forecast["native_wind_speed"] = entry["wind_speed"]

            if "wind_dir" in entry:
                forecast["wind_bearing"] = entry["wind_dir"]

            if "humidity" in entry:
                forecast["humidity"] = entry["humidity"]

            if "precipitation" in entry:
                forecast["native_precipitation"] = entry["precipitation"]

            if "cloud_cover" in entry:
                # Estimate condition from cloud cover
                cloud = entry["cloud_cover"]
                if cloud < 20:
                    forecast["condition"] = "sunny"
                elif cloud < 60:
                    forecast["condition"] = "partlycloudy"
                else:
                    forecast["condition"] = "cloudy"

            forecasts.append(forecast)

        return forecasts

