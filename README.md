# DMI Weather for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/aleksanderbl29/dmi-homeassistant.svg)](https://github.com/aleksanderbl29/dmi-homeassistant/releases)
[![codecov](https://codecov.io/gh/aleksanderbl29/dmi-homeassistant/branch/main/graph/badge.svg)](https://codecov.io/gh/aleksanderbl29/dmi-homeassistant)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant custom integration for weather and sea-level data from the Danish
Meteorological Institute (DMI).

## Features

- **No API key required** - DMI's open data API is freely available
- Weather entity with current conditions
- Hourly forecast support
- Multiple sensor entities:
  - Temperature
  - Dew Point
  - Humidity
  - Atmospheric Pressure
  - Wind Speed & Gusts
  - Wind Direction
  - Precipitation
  - Visibility
  - Cloud Cover
  - Solar Radiation
  - Last Successful Update (diagnostic timestamp)
- Support for all active DMI weather stations in Denmark, Greenland, and the Faroe Islands
- Tide-gauge sensors for sea level and water temperature
- Danish and English translations

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add `https://github.com/aleksanderbl29/dmi-homeassistant` as a custom repository with category "Integration"
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/aleksanderbl29/dmi-homeassistant/releases)
2. Extract the `custom_components/dmi` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "DMI Weather"
4. Choose a normal weather station, an advanced composite weather source, or a sea-level
   station
5. Select the station from the dropdown list
6. For weather setups, optionally enable "Use Home Assistant coordinates for forecasts"

### Options

After setup, you can configure:
- **Update interval**: How often to fetch new data (10-60 minutes)
- **Include forecast**: Enable/disable hourly forecast data

## Entities

### Weather Entity

The main weather entity provides:
- Current condition (sunny, cloudy, rainy, etc.)
- Temperature
- Humidity
- Pressure
- Wind speed and direction
- Visibility
- Hourly forecast (if enabled)

### Sensors

Depending on what the selected station reports, you may get sensors for:

| Sensor | Unit | Description |
|--------|------|-------------|
| Temperature | °C | Current air temperature |
| Dew Point | °C | Dew point temperature |
| Humidity | % | Relative humidity |
| Pressure | hPa | Atmospheric pressure at sea level |
| Wind Speed | m/s | Current wind speed |
| Wind Gust | m/s | Maximum wind gust |
| Wind Direction | ° | Wind direction in degrees |
| Precipitation | mm | Precipitation in the last hour |
| Visibility | m | Horizontal visibility |
| Cloud Cover | % | Cloud coverage percentage |
| Solar Radiation | W/m² | Global solar radiation |
| Last Successful Update | timestamp | Time of the last successful data fetch from DMI |

> **Note**: Not all stations report all parameters. The integration only creates sensors for parameters the selected station actually provides.
> The diagnostic `Last Successful Update` sensor is always created for a configured station.

### Sea-level Sensors

The sea-level setup uses DMI's oceanographic observation service. Depending on what the
selected tide gauge reports, the integration creates:

| Sensor | Unit | Description |
|--------|------|-------------|
| Sea Level DVR90 | cm | Sea level relative to Danish Vertical Reference 1990 |
| Sea Level Local Reference | cm | Sea level relative to the station's local zero |
| Sea Level Registration | cm | Sea-level registration (Coastal Authority data uses DVR90) |
| Water Temperature | °C | Supporting harbor water-temperature measurement |
| Predicted Sea Level | cm | Next 10-minute astronomical tide prediction with a 24-hour series |
| Next High Tide | cm | Next predicted astronomical high tide and its timestamp |
| Next Low Tide | cm | Next predicted astronomical low tide and its timestamp |
| DKSS Forecast Sea Level | cm | Weather-driven sea-level deviation forecast for up to five days |
| Last Successful Update | timestamp | Time of the last successful data fetch from DMI |

Sea-level readings also expose their observation timestamp, API creation timestamp when
available, and DMI quality-control status as state attributes. Water-temperature measurements
are taken inside harbors and are not standardized measurements of the undisturbed sea surface.

DMI uses a separate station catalog for astronomical tide predictions. During setup, the
nearest prediction point is selected by default and can be changed before the entry is created.
The predicted-level sensor includes the next 24 hours of 10-minute values in its `forecast`
attribute, as well as summaries of the next high and low tide. These are astronomical tide
predictions; they do not include weather-driven storm-surge effects from DMI's DKSS model.

The separate DKSS sensor uses the observation station coordinates to select the most detailed
available DMI storm-surge model and the closest modelled water grid cell. It exposes the hourly
forecast, forecast high and low, model collection, and model coordinates as attributes. DKSS
values are deviations from mean sea level and therefore must not be treated as directly
equivalent to observed DVR90 or local-reference levels.

## Data Sources And API Keys

This integration uses DMI's Open Data API at `opendataapi.dmi.dk`. The API is open and requires no authentication on the endpoints used here.

- `metObs` observations via `https://opendataapi.dmi.dk/v2/metObs`: no API key
- `oceanObs` observations via `https://opendataapi.dmi.dk/v2/oceanObs`: no API key
- Forecast EDR via `https://opendataapi.dmi.dk/v1/forecastedr`: no API key
- No Home Assistant secrets, options, or config-flow fields are used for API keys
- The deprecated `dmigw.govcloud.dk` hostname is not used

### Source Matrix

- **Observations**: Real-time data from DMI weather stations
- **Sea-level observations**: Tide-gauge data from DMI and the Danish Coastal Authority
- **Storm-surge forecasts**: Coordinate-based sea-level deviations from DMI's DKSS model
- **Forecasts**: HARMONIE-DINI model forecasts

| Data | Endpoint | API key | Used by default |
|---|---|---:|---:|
| Station observations | DMI metObs v2 | No | Yes |
| Sea-level observations | DMI oceanObs v2 | No | For sea-level setups |
| HARMONIE forecast point data | DMI Forecast EDR v1 | No | Yes |
| Deprecated DMI gateway | `dmigw.govcloud.dk` | Yes | No |

The integration remains API-key-free by default. Authenticated DMI sources must be opt-in, documented, and reviewed separately before use.

### Rate Limiting

The API has rate limits. The default update interval of 10 minutes should be well within limits for normal use.

## Troubleshooting

### No sensors appearing

Some stations (like Pluvio rain gauges) only report specific parameters. Try selecting a different station with more sensors.

### Forecast not available

Forecast requires coordinates. Enable "Use Home Assistant coordinates for forecasts" or ensure the selected station has valid coordinates.

### Connection errors

Check your internet connection. The integration will automatically retry when connectivity is restored.
During transient upstream failures, the integration may continue serving cached data. The `Last Successful Update` sensor will stay unchanged until a fresh fetch succeeds.

### HTTP 429 errors

HTTP 429 means DMI fair-use or rate limiting, not a missing API key. Increase the update interval or wait before retrying.

### HTTP 401 or 403 errors

HTTP 401 or 403 would indicate the wrong hostname or an upstream DMI change, because the current supported hostname, `opendataapi.dmi.dk`, does not require authentication. The deprecated `dmigw.govcloud.dk` gateway requires authentication and is not used by this integration.

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not affiliated with or endorsed by DMI. Weather data is provided by DMI's open data initiative.

## Links

- [DMI Open Data](https://opendataapi.dmi.dk/)
- [Home Assistant](https://www.home-assistant.io/)
- [HACS](https://hacs.xyz/)
