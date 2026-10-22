# EMT València for Home Assistant

Custom HACS integration for EMT València. It finds stops near selected Home
Assistant Companion devices, monitors favourite stops and exposes arrivals
without an external service, token, YAML configuration or LXC.

Version 0.5.0 replaces the encoded favourite-stop text field with a searchable
picker and a separate optional alias. Version 0.4.2 retries a nearby stop that
has no successful arrival snapshot yet, independently of the favourite-stop
schedule. Version 0.4.1 restores
the upstream EMT request headers for arrivals. EMT
returns a HTTP 200 XML error page when those headers are absent; an all-error
response is now treated as a failed refresh and cannot advance
`last_successful_update`.

## Installation and update

In **HACS → Integrations → ⋮ → Custom repositories**, add
`https://github.com/davidcbe/ha-emt-valencia` as **Integration**. Download or
update it, restart Home Assistant, then add **EMT València** in **Settings →
Devices & services**. Existing configuration and entity IDs are retained.

## Configuration

Selecciona uno o más dispositivos registrados mediante **Home Assistant
Companion**. La integración elige automáticamente el rastreador GPS adecuado.
Las favoritas se gestionan desde **Configurar → Gestionar paradas favoritas**:
busca la parada por nombre, selecciónala y escribe el alias opcional en su
propio campo. No tienes que conocer ni escribir la sintaxis de los IDs.

## Refresh behaviour

All intervals are configurable in seconds. Defaults are 300 s for nearby
stops while tracker presence is `home`, 60 s while away, and 300 s for
favourites. GPS unavailable or outside a conservative València city envelope
does not create a nearby-stop query. Favourites do not depend on GPS.

The integration shares one result per stop: a stop found by several mobiles or
also marked favourite is queried once. Nearby metadata and the city catalogue
are cached to supply favourite names and coordinates. Concurrent requests are
coalesced.

These button entities request an immediate EMT query, safely reusing an active
request on repeated presses:

- `button.emt_valencia_actualizar_favoritas`
- `button.emt_valencia_actualizar_paradas_cercanas`
- `button.emt_valencia_actualizar_emt`

Temporary failures retain prior arrivals, set `stale`, use a 12-second timeout,
one retry and bounded progressive backoff. A failed stop does not block others.

## Sensors and data

Existing per-device nearby sensors and per-favourite sensors remain unchanged:
they keep `nearby_stops` and `arrivals`. The dynamic aggregate
`sensor.emt_valencia_paradas_favoritas` has state equal to the number of
favourites and a `favorite_stops` list.

Every favourite list item exposes `stop_id`, `name`, `official_name`,
`custom_name`, `latitude`, `longitude`, `arrivals` and `next_minutes`.
Nearby stops keep their `distance_m` and stop number. `last_successful_update`
records the last successful EMT response.

Arrivals preserve `line`, `destination` and `minutes`. They add:

- `time_type: estimated`, `observed_at` and `estimated_arrival` for minute
  estimates. The timestamp is calculated from the EMT query instant in
  `Europe/Madrid`, not a dashboard/browser clock.
- `time_type: scheduled`, `arrival_time`, `scheduled_arrival` and
  `scheduled_date_inferred: true` for a clock-time supplied by EMT. A scheduled
  time is never represented as a live GPS estimate.
- `time_type: error` for malformed or EMT error records.

This provides the future-card data for presentations such as `9 min (17:08)`.
No Lovelace card is installed or modified.

## EMT data and known limitations

The upstream `emtvlcapi` library is retained for stop discovery. Its
`get_bus_times()` treats a value such as `18:08:00` in the XML `minutos` field
as an error; EMT returned exactly that for stop 1585. The integration therefore
locally parses arrival XML only, retaining it as a scheduled arrival, without
modifying the third-party library.

No official documented quota or verified meaning for EMT's occasional warning
icon has been found. No meaning is assigned to it. Caching, de-duplication,
timeouts and backoff reduce requests, but EMT may change or restrict its public
endpoints without notice.

## Validation after update

In **Developer tools → States**, check a tracker, favourite and aggregate
sensor. Press each update button and check `last_successful_update`. Change an
alias in options and confirm it appears as `name`, alongside `official_name`
and coordinates in `favorite_stops` after the automatic reload.
