# Google Air Quality (Custom)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Real-time air quality for Home Assistant, powered by the [Google Air Quality API](https://developers.google.com/maps/documentation/air-quality) — plus `gaqi`, a standalone CLI for querying the same data from a terminal or script.

One device per location. Pick exactly the sensors you want. Universal or regional AQI, in the right units, always up to date.

## Features

- A clean Home Assistant device for every location you track.
- Choose your sensors: AQI, PM2.5, PM10, CO, NO2, O3, SO2, health recommendations, data timestamp.
- Universal (Google) or regional (local authority) AQI, including custom local AQI indexes.
- Fully UI-driven setup — no YAML to write or maintain.
- Built-in re-authentication and reconfigure flows.
- `gaqi`: a fast standalone CLI for air quality data, no Home Assistant required.

## Get a Google API key

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or pick an existing one).
2. Under **Billing**, link a billing account to the project — this is required by Google Maps Platform APIs, even within the free usage tier.
3. Go to **APIs & Services → Library**, search for **Air Quality API**, and click **Enable**.
4. Go to **APIs & Services → Credentials → Create credentials → API key**. Copy the key.
5. Click the key, then **API restrictions → Restrict key**, and select only **Air Quality API**. Save.
6. Optional: under **Application restrictions → IP addresses**, restrict the key to your Home Assistant's public IP (skip this if your IP is dynamic).
7. Recommended: set a daily quota under **APIs & Services → Air Quality API → Quotas**, and add a budget alert under **Billing → Budgets & alerts**.
8. Expected usage: 1 request per location every 30 minutes ≈ 48/day ≈ 1,440/month per location. Check current pricing and free allowance at <https://developers.google.com/maps/billing-and-pricing/pricing>.

## Install via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jakcyl&repository=google-air-quality&category=integration)

HACS → ⋮ → **Custom repositories** → add `https://github.com/jakcyl/google-air-quality` with category **Integration** → **Download** → restart Home Assistant.

## Manual install

Copy `custom_components/google_air_quality_custom` into `<config>/custom_components/` and restart Home Assistant.

## Configure

**Settings → Devices & services → Add integration** → search for "Google Air Quality (Custom)" → enter your API key and language.

Then, on the integration's card, click **Add location** and fill in:

- **Name** — used as the device name.
- **Location** — a map pin for the air quality station.
- **AQI source** — universal (Google) or regional (local authority).
- Optional custom local AQI: a **region code** (e.g. `IT`) and a **local AQI id** (e.g. `ita_moniqa`) — see the [list of local AQIs](https://developers.google.com/maps/documentation/air-quality/laqis).
- **Sensors** — which entities to create for this location.

## Entities

| key | translation_key | device_class | unit | value |
|---|---|---|---|---|
| aqi | `aqi` | AQI | — | AQI index value |
| pm25 | — | PM25 | µg/m³ | PM2.5 concentration |
| pm10 | — | PM10 | µg/m³ | PM10 concentration |
| co | — | CO | ppm | carbon monoxide |
| no2 | — | NITROGEN_DIOXIDE | µg/m³ | nitrogen dioxide |
| o3 | — | OZONE | µg/m³ | ozone |
| so2 | — | SULPHUR_DIOXIDE | µg/m³ | sulphur dioxide |
| health_recommendations | `health_recommendations` | — | — | general population health text |
| data_timestamp | `data_timestamp` | TIMESTAMP | — | when the data was recorded |

## Units

Google returns gases (CO, NO2, O3, SO2) in parts per billion; this integration converts them to µg/m³ at
25 °C / 1 atm (CO is reported in ppm instead, per its Home Assistant device class). PM2.5 and PM10 are already
in µg/m³ and are passed through unchanged.

## CLI usage

Install the CLI from a checkout of this repository (no PyPI package is published):

```bash
pip install .
# or, for isolated global install:
pipx install .
```

Then query a location:

```bash
gaqi --api-key YOUR_KEY --lat 45.07 --lon 7.69
```

The API key and coordinates can also come from environment variables:

```bash
export GOOGLE_AQI_API_KEY=YOUR_KEY
export GOOGLE_AQI_LAT=45.07
export GOOGLE_AQI_LON=7.69
gaqi --json
```

Run `gaqi --help` for all options (language, AQI source, custom local AQI, sensor selection).

## Migrating from the REST sensor

Remove the old `rest:` sensor block from your YAML configuration, restart Home Assistant, then add this
integration via the UI. Entity IDs will differ from the old REST sensor — update any dashboards or
automations that reference them.

## Development

```bash
scripts/setup    # create a venv and install dependencies (including the gaqi CLI, editable)
scripts/develop  # run Home Assistant with this integration at http://localhost:8123
scripts/lint     # ruff format + check, mypy --strict
pytest           # run the test suite
```

For CLI-only development: `pip install -e .` then run `gaqi ...` directly against your changes.
