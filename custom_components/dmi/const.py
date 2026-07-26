"""Constants for the DMI Weather integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory

DOMAIN = "dmi"
ATTRIBUTION = "Data provided by DMI Open Data"

# API URLs
BASE_URL = "https://opendataapi.dmi.dk"
METOBS_URL = f"{BASE_URL}/v2/metObs"
OCEANOBS_URL = f"{BASE_URL}/v2/oceanObs"
FORECAST_URL = f"{BASE_URL}/v1/forecastedr"

# Update interval in seconds (10 minutes)
DEFAULT_UPDATE_INTERVAL = 600

# Config keys
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_USE_COORDINATES = "use_coordinates"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_INCLUDE_FORECAST = "include_forecast"
CONF_SETUP_TYPE = "setup_type"
CONF_BACKUP_STATIONS = "backup_stations"
CONF_BACKUP_PARAMETERS = "parameters"
CONF_BACKUP_ALLOW_OVERRIDE = "allow_override"  # legacy, ignored since v1.2
CONF_BACKUP_STATION_NAME_SUFFIX = "backup_station_name_suffix"
CONF_SOURCE_STATION_ID = "source_station_id"
CONF_SOURCE_STATION_NAME = "source_station_name"
CONF_SOURCE_TYPE = "source_type"
CONF_TIDEWATER_STATION_ID = "tidewater_station_id"
CONF_TIDEWATER_STATION_NAME = "tidewater_station_name"
CONF_TIDEWATER_LATITUDE = "tidewater_latitude"
CONF_TIDEWATER_LONGITUDE = "tidewater_longitude"
CONF_LOW_ASTRONOMICAL_TIDE = "low_astronomical_tide"
CONF_MEAN_LOW_WATER_SPRING = "mean_low_water_spring"

SETUP_TYPE_NORMAL = "normal"
SETUP_TYPE_ADVANCED = "advanced"
SETUP_TYPE_SEA = "sea"
SOURCE_TYPE_PRIMARY = "primary"
SOURCE_TYPE_BACKUP = "backup"

# WMO Weather Code to Home Assistant condition mapping
CONDITION_MAP: dict[int, str] = {
    0: "sunny",
    1: "sunny",
    2: "partlycloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "rainy",
    53: "rainy",
    55: "rainy",
    56: "rainy",
    57: "rainy",
    61: "rainy",
    63: "rainy",
    65: "pouring",
    66: "snowy-rainy",
    67: "snowy-rainy",
    71: "snowy",
    73: "snowy",
    75: "snowy",
    77: "snowy",
    80: "rainy",
    81: "rainy",
    82: "pouring",
    85: "snowy",
    86: "snowy",
    95: "lightning-rainy",
    96: "hail",
    99: "hail",
}


def _sensor(
    key: str,
    name: str,
    *,
    native_unit_of_measurement: str | None = None,
    device_class: SensorDeviceClass | None = None,
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
    icon: str | None = None,
) -> SensorEntityDescription:
    """Build a sensor entity description."""
    return SensorEntityDescription(
        key=key,
        name=name,
        native_unit_of_measurement=native_unit_of_measurement,
        device_class=device_class,
        state_class=state_class,
        icon=icon,
    )


SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    _sensor(
        "temp_dry",
        "Temperature",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_dew",
        "Dew Point",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_mean_past1h",
        "Mean Temperature Last Hour",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_max_past1h",
        "Maximum Temperature Last Hour",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_min_past1h",
        "Minimum Temperature Last Hour",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_max_past12h",
        "Temperature Max Last 12 Hours",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_min_past12h",
        "Temperature Min Last 12 Hours",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_grass",
        "Grass Temperature",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_grass_mean_past1h",
        "Mean Grass Temperature Last Hour",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_grass_max_past1h",
        "Maximum Grass Temperature Last Hour",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "temp_grass_min_past1h",
        "Minimum Grass Temperature Last Hour",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _sensor(
        "humidity",
        "Humidity",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    _sensor(
        "humidity_past1h",
        "Humidity Last Hour",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    _sensor(
        "pressure",
        "Pressure",
        native_unit_of_measurement="hPa",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
    ),
    _sensor(
        "pressure_at_sea",
        "Sea Level Pressure",
        native_unit_of_measurement="hPa",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
    ),
    _sensor(
        "wind_speed",
        "Wind Speed",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
    ),
    _sensor(
        "wind_speed_past1h",
        "Wind Speed Last Hour",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
    ),
    _sensor(
        "wind_max",
        "Wind Gust",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
    ),
    _sensor(
        "wind_min",
        "Minimum Wind Speed",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
    ),
    _sensor(
        "wind_min_past1h",
        "Minimum Wind Speed Last Hour",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
    ),
    _sensor(
        "wind_max_per10min_past1h",
        "Maximum 10-Minute Wind Speed Last Hour",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
    ),
    _sensor(
        "wind_gust_always_past1h",
        "Wind Gust Last Hour",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
    ),
    _sensor(
        "wind_dir",
        "Wind Direction",
        native_unit_of_measurement="°",
        icon="mdi:compass-outline",
    ),
    _sensor(
        "wind_dir_past1h",
        "Wind Direction Last Hour",
        native_unit_of_measurement="°",
        icon="mdi:compass-outline",
    ),
    _sensor(
        "precip_past1min",
        "Precipitation Last Minute",
        native_unit_of_measurement="mm",
        device_class=SensorDeviceClass.PRECIPITATION,
    ),
    _sensor(
        "precip_past10min",
        "Precipitation Last 10 Minutes",
        native_unit_of_measurement="mm",
        device_class=SensorDeviceClass.PRECIPITATION,
    ),
    _sensor(
        "precip_past1h",
        "Precipitation Last Hour",
        native_unit_of_measurement="mm",
        device_class=SensorDeviceClass.PRECIPITATION,
    ),
    _sensor(
        "precip_dur_past10min",
        "Precipitation Duration Last 10 Minutes",
        native_unit_of_measurement="min",
    ),
    _sensor(
        "precip_dur_past1h",
        "Precipitation Duration Last Hour",
        native_unit_of_measurement="min",
    ),
    _sensor(
        "visibility",
        "Visibility",
        native_unit_of_measurement="m",
        device_class=SensorDeviceClass.DISTANCE,
    ),
    _sensor(
        "visib_mean_last10min",
        "Mean Visibility Last 10 Minutes",
        native_unit_of_measurement="m",
        device_class=SensorDeviceClass.DISTANCE,
    ),
    _sensor(
        "cloud_cover",
        "Cloud Cover",
        native_unit_of_measurement="%",
        icon="mdi:cloud",
    ),
    _sensor(
        "cloud_height",
        "Cloud Height",
        native_unit_of_measurement="m",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:cloud-outline",
    ),
    _sensor("weather", "Weather", icon="mdi:weather-partly-cloudy", state_class=None),
    _sensor(
        "radia_glob",
        "Solar Radiation",
        native_unit_of_measurement="W/m²",
        device_class=SensorDeviceClass.IRRADIANCE,
    ),
    _sensor(
        "radia_glob_past1h",
        "Solar Radiation Last Hour",
        native_unit_of_measurement="Wh/m²",
        icon="mdi:weather-sunny",
    ),
    _sensor(
        "sun_last10min_glob",
        "Sunshine Last 10 Minutes",
        native_unit_of_measurement="min",
        icon="mdi:white-balance-sunny",
    ),
    _sensor(
        "sun_last1h_glob",
        "Sunshine Last Hour",
        native_unit_of_measurement="min",
        icon="mdi:white-balance-sunny",
    ),
)

SENSOR_TYPES_BY_KEY: dict[str, SensorEntityDescription] = {
    description.key: description for description in SENSOR_TYPES
}

SEA_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    _sensor(
        "sealev_dvr",
        "Sea Level DVR90",
        native_unit_of_measurement="cm",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:waves-arrow-up",
    ),
    _sensor(
        "sealev_ln",
        "Sea Level Local Reference",
        native_unit_of_measurement="cm",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:waves-arrow-up",
    ),
    _sensor(
        "sea_reg",
        "Sea Level Registration",
        native_unit_of_measurement="cm",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:waves-arrow-up",
    ),
    _sensor(
        "tw",
        "Water Temperature",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-water",
    ),
)

SEA_SENSOR_TYPES_BY_KEY: dict[str, SensorEntityDescription] = {
    description.key: description for description in SEA_SENSOR_TYPES
}

TIDEWATER_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    _sensor(
        "predicted_sea_level",
        "Predicted Sea Level",
        native_unit_of_measurement="cm",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:waves-arrow-right",
    ),
    _sensor(
        "next_high_tide",
        "Next High Tide",
        native_unit_of_measurement="cm",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:waves-arrow-up",
    ),
    _sensor(
        "next_low_tide",
        "Next Low Tide",
        native_unit_of_measurement="cm",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:waves-arrow-down",
    ),
)

DKSS_FORECAST_SENSOR = _sensor(
    "dkss_forecast_sea_level",
    "DKSS Forecast Sea Level",
    native_unit_of_measurement="cm",
    device_class=SensorDeviceClass.DISTANCE,
    icon="mdi:waves-arrow-right",
)

LAST_FETCH_SENSOR = SensorEntityDescription(
    key="last_fetch",
    name="Last Successful Update",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:clock-check-outline",
)
