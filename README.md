# EMT València for Home Assistant

Custom integration, prepared for installation as a HACS custom repository.
It fetches the real-time arrivals for one or more EMT València stops directly
from Home Assistant; it does not require an LXC, HTTP service, token, or YAML
configuration.

## Current scope (0.3.0)

Each config entry can create bounded aggregate sensors (no dynamic entity flood):

- One sensor per selected Home Assistant Companion device, containing structured `nearby_stops`
  ordered by distance, each with lines, destinations and arrivals.
- One sensor per optional favourite stop, with its structured `arrivals`.
- A permanent `sensor.emt_valencia_paradas_favoritas` aggregate: its state is
  the number of configured favourites and its `favorite_stops` attribute holds
  every stop, arrival list and next numeric arrival for one dynamic dashboard card.
- Shared live-arrival calls: a stop found for multiple mobiles or also marked as
  favourite is queried only once per refresh.
- GPS stop search only repeats after the configured movement threshold; arrivals
  refresh at the configured interval (60 seconds by default).
- Devices left without entities after a configuration change can be removed from
  Home Assistant's device registry.

There is no mandatory stop. Existing 0.1 entries preserve their old stop as an
editable favourite, so the test stop **1622** can simply be removed in Options.

## Install with HACS

1. Put this directory in a GitHub repository. The `custom_components` folder
   must remain at the repository root.
2. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
3. Add the repository URL, select **Integration**, then download **EMT
   València**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**, search for
   **EMT València**. Pick the phones or watches registered through Home
   Assistant Companion (each appears once; EMT selects its GPS tracker
   automatically) and/or enter favourites as `1585:Casa, 1622:Trabajo`.

HACS only installs the integration. On first setup Home Assistant installs the
declared Python dependency `emtvlcapi==1.0.0` automatically.

## Test after installation

Open **Developer tools → States**, find the new EMT sensor, and confirm that:

- Its state is a minute count for the next arriving bus (or `unknown` if EMT
  currently returns only clock-time/error records).
- A tracker sensor's `nearby_stops` lists stop IDs, distance, lines and arrivals.
- A favourite sensor's `arrivals` contains its live services.
- Use the entity's standard **Update** action to request a manual refresh.

If setup fails, enable debug logging for the `emt_valencia` integration and
check the Home Assistant log. The integration leaves all other Home Assistant
configuration untouched.

## Planned extensions

The coordinator is deliberately separated from the sensor so future work can
add, without an external service:

1. a dashboard card using the stable aggregate attributes;
2. optional automatic presentation based on presence at home.

## Upstream dependency

This integration uses [EMTValencia-API](https://github.com/ElEd0/EMTValencia-API)
(`emtvlcapi`), whose public API exposes `get_bus_times` and
`get_stops_in_extent`.
