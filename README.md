# EMT València for Home Assistant

Custom integration, prepared for installation as a HACS custom repository.
It fetches the real-time arrivals for one or more EMT València stops directly
from Home Assistant; it does not require an LXC, HTTP service, token, or YAML
configuration.

## Current scope (0.1.0)

Each config entry creates one sensor:

- `sensor.emt_valencia_parada_<stop>_proxima_llegada` (the actual slug is
  assigned by Home Assistant): earliest minute-based prediction.
- `arrivals` attribute: complete list returned by EMT, including `linea`,
  `destino`, and either `minutos`, `horaLlegada`, or an EMT `error`.
- Refresh: every minute, coordinated so future entities share one API call.

The configuration flow defaults to stop **1622**, which was used as the live
smoke-test stop during development.

## Install with HACS

1. Put this directory in a GitHub repository. The `custom_components` folder
   must remain at the repository root.
2. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
3. Add the repository URL, select **Integration**, then download **EMT
   València**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**, search for
   **EMT València**, and enter the stop number (use `1622` for the initial
   test).

HACS only installs the integration. On first setup Home Assistant installs the
declared Python dependency `emtvlcapi==1.0.0` automatically.

## Test after installation

Open **Developer tools → States**, find the new EMT sensor, and confirm that:

- Its state is a minute count for the next arriving bus (or `unknown` if EMT
  currently returns only clock-time/error records).
- The `arrivals` attribute contains live data for the chosen stop.
- Updating the entity after a minute changes the data when EMT publishes a new
  estimate.

If setup fails, enable debug logging for the `emt_valencia` integration and
check the Home Assistant log. The integration leaves all other Home Assistant
configuration untouched.

## Planned extensions

The coordinator is deliberately separated from the sensor so future work can
add, without an external service:

1. stop discovery using `emtvlcapi.get_stops_in_extent`;
2. nearest-stop selection from a configured `device_tracker`;
3. per-line arrival entities and a Lovelace card built on the `arrivals`
   attribute.

## Upstream dependency

This integration uses [EMTValencia-API](https://github.com/ElEd0/EMTValencia-API)
(`emtvlcapi`), whose public API exposes `get_bus_times` and
`get_stops_in_extent`.
