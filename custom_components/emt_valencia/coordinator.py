"""Polling, cache and request de-duplication for EMT València."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from math import asin, cos, radians, sin, sqrt
import re
from typing import Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import emtvlcapi
from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AWAY_SCAN_INTERVAL, CONF_DEVICE_TRACKERS, CONF_FAVORITE_STOPS,
    CONF_FAVORITES_SCAN_INTERVAL, CONF_HOME_SCAN_INTERVAL, CONF_MAX_NEARBY_STOPS,
    CONF_MOBILE_DEVICES, CONF_MOVEMENT_THRESHOLD, CONF_SCAN_INTERVAL, CONF_SEARCH_RADIUS,
    CONF_STOP_ID, DEFAULT_AWAY_SCAN_INTERVAL, DEFAULT_FAVORITES_SCAN_INTERVAL,
    DEFAULT_HOME_SCAN_INTERVAL, DEFAULT_MAX_NEARBY_STOPS, DEFAULT_MOVEMENT_THRESHOLD,
    DEFAULT_SCAN_INTERVAL, DEFAULT_SEARCH_RADIUS, DOMAIN, MAX_BACKOFF, REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)
_TZ = ZoneInfo("Europe/Madrid")
_BUS_TIMES_URL = "https://www.emtvalencia.es/EMT/mapfunctions/MapUtilsPetitions.php?sec=getSAE"
# EMT rejects the arrival endpoint when it is called without the same browser
# headers used by emtvlcapi.  Keep this explicit rather than relying on that
# library's non-public module variable: this integration owns the small XML
# parser needed for clock-time rows in ``minutos``.
_EMT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:78.0) Gecko/20100101 Firefox/98.0",
    "Accept": "*/*",
    "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
    "Referer": "https://www.emtvalencia.es",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}
# Conservative city envelope: no nearby-stop request outside it.
_CATALOG_BOUNDS = (39.35, -0.50, 39.55, -0.20)
_CLOCK = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")


def distance_m(a: float, b: float, c: float, d: float) -> int:
    x, y = radians(c - a), radians(d - b)
    h = sin(x / 2) ** 2 + cos(radians(a)) * cos(radians(c)) * sin(y / 2) ** 2
    return round(6_371_000 * 2 * asin(sqrt(h)))


def coords(state: Any) -> tuple[float, float] | None:
    if state is None or state.state in {"unknown", "unavailable"}:
        return None
    try:
        lat, lon = float(state.attributes["latitude"]), float(state.attributes["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def _in_emt_area(position: tuple[float, float]) -> bool:
    south, west, north, east = _CATALOG_BOUNDS
    return south <= position[0] <= north and west <= position[1] <= east


class EMTValenciaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One shared coordinator with separate nearby and favourite schedules."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._locations: dict[str, tuple[float, float]] = {}
        self._nearby_due: dict[str, datetime] = {}
        self._favorite_due: dict[str, datetime] = {}
        self._arrival_cache: dict[str, dict[str, Any]] = {}
        self._arrival_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self._catalog: dict[str, dict[str, Any]] = {}
        self._catalog_loaded = False
        self._unsub = None
        self._force_nearby = self._force_favorites = False
        self._backoff_until: datetime | None = None
        self._error_count = 0
        super().__init__(hass, logger=_LOGGER, name=DOMAIN, update_interval=DEFAULT_SCAN_INTERVAL)
        self.update_interval = timedelta(seconds=min(self.config[CONF_HOME_SCAN_INTERVAL], self.config[CONF_AWAY_SCAN_INTERVAL], self.config[CONF_FAVORITES_SCAN_INTERVAL]))

    @property
    def config(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            CONF_DEVICE_TRACKERS: [], CONF_MOBILE_DEVICES: [], CONF_FAVORITE_STOPS: [],
            CONF_SEARCH_RADIUS: DEFAULT_SEARCH_RADIUS, CONF_MAX_NEARBY_STOPS: DEFAULT_MAX_NEARBY_STOPS,
            CONF_SCAN_INTERVAL: int(DEFAULT_SCAN_INTERVAL.total_seconds()),
            CONF_HOME_SCAN_INTERVAL: DEFAULT_HOME_SCAN_INTERVAL,
            CONF_AWAY_SCAN_INTERVAL: DEFAULT_AWAY_SCAN_INTERVAL,
            CONF_FAVORITES_SCAN_INTERVAL: DEFAULT_FAVORITES_SCAN_INTERVAL,
            CONF_MOVEMENT_THRESHOLD: DEFAULT_MOVEMENT_THRESHOLD,
        }
        result.update(self.entry.data)
        result.update(self.entry.options)
        if CONF_AWAY_SCAN_INTERVAL not in self.entry.data and CONF_AWAY_SCAN_INTERVAL not in self.entry.options:
            result[CONF_AWAY_SCAN_INTERVAL] = result[CONF_SCAN_INTERVAL]
        if CONF_STOP_ID in self.entry.data and not self.entry.options:
            result[CONF_FAVORITE_STOPS] = [{"stop_id": str(self.entry.data[CONF_STOP_ID]), "name": ""}]
        return result

    @property
    def tracker_keys(self) -> list[str]:
        return self.config[CONF_MOBILE_DEVICES] if (CONF_MOBILE_DEVICES in self.entry.data or CONF_MOBILE_DEVICES in self.entry.options) else self.config[CONF_DEVICE_TRACKERS]

    def _tracker_for_key(self, key: str) -> tuple[str | None, str]:
        if key.startswith("device_tracker."):
            state = self.hass.states.get(key)
            return key, state.name if state else key
        device = dr.async_get(self.hass).async_get(key)
        name = (device.name_by_user or device.name) if device else key
        candidates = [item.entity_id for item in er.async_entries_for_device(er.async_get(self.hass), key) if item.domain == "device_tracker" and item.platform == "mobile_app"]
        entity_id = next((item for item in candidates if coords(self.hass.states.get(item))), None)
        return entity_id or (candidates[0] if candidates else None), name

    def async_start(self) -> Any:
        entities = [entity_id for key in self.tracker_keys if (entity_id := self._tracker_for_key(key)[0])]
        if entities:
            self._unsub = async_track_state_change_event(self.hass, entities, self._tracker_changed)
        return self.async_shutdown

    @callback
    def async_shutdown(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _tracker_changed(self, event: Event) -> None:
        entity_id, new = event.data["entity_id"], coords(event.data.get("new_state"))
        key = next((item for item in self.tracker_keys if self._tracker_for_key(item)[0] == entity_id), entity_id)
        old = self._locations.get(key)
        if new and (old is None or distance_m(*old, *new) >= self.config[CONF_MOVEMENT_THRESHOLD]):
            self._force_nearby = True
            self.async_request_refresh()

    async def async_refresh_nearby(self) -> None:
        self._force_nearby = True
        await self.async_request_refresh()

    async def async_refresh_favorites(self) -> None:
        self._force_favorites = True
        await self.async_request_refresh()

    async def async_refresh_all(self) -> None:
        self._force_nearby = self._force_favorites = True
        await self.async_request_refresh()

    @staticmethod
    def _normalise_stop(row: dict[str, Any]) -> dict[str, Any] | None:
        try:
            lat, lon, stop_id = float(row["lat"]), float(row["lon"]), str(row["stopId"])
        except (KeyError, TypeError, ValueError):
            return None
        name = row.get("name") or row.get("ubica") or "Parada EMT"
        return {"stop_id": stop_id, "name": name, "official_name": name, "latitude": lat, "longitude": lon,
                "lines": [{"line": route.get("SN") or route.get("lineaNumber") or route.get("id_linea"), "destination": route.get("headSign") or route.get("LN") or route.get("lineaName")} for route in row.get("routes", []) if isinstance(route, dict)]}

    async def _nearby(self, latitude: float, longitude: float) -> list[dict[str, Any]]:
        radius = self.config[CONF_SEARCH_RADIUS]
        lat_delta, lon_delta = radius / 111_320, radius / max(1, 111_320 * cos(radians(latitude)))
        rows = await asyncio.wait_for(self.hass.async_add_executor_job(emtvlcapi.get_stops_in_extent, latitude-lat_delta, longitude-lon_delta, latitude+lat_delta, longitude+lon_delta), timeout=REQUEST_TIMEOUT)
        stops: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            item = self._normalise_stop(row)
            if item:
                item["distance_m"] = distance_m(latitude, longitude, item["latitude"], item["longitude"])
                if item["distance_m"] <= radius:
                    stops.append(item)
                    self._catalog[item["stop_id"]] = dict(item)
        return sorted(stops, key=lambda item: item["distance_m"])[:self.config[CONF_MAX_NEARBY_STOPS]]

    async def _ensure_catalog(self) -> None:
        if self._catalog_loaded:
            return
        try:
            rows = await asyncio.wait_for(self.hass.async_add_executor_job(emtvlcapi.get_stops_in_extent, *_CATALOG_BOUNDS), timeout=REQUEST_TIMEOUT)
            for row in rows if isinstance(rows, list) else []:
                if item := self._normalise_stop(row):
                    self._catalog[item["stop_id"]] = item
            self._catalog_loaded = True
        except Exception as err:
            _LOGGER.warning("Could not load EMT stop catalogue: %s", err)

    async def _arrivals(self, stop_id: str) -> dict[str, Any]:
        if task := self._arrival_tasks.get(stop_id):
            return await task
        task = self.hass.async_create_task(self._fetch_arrivals(stop_id))
        self._arrival_tasks[stop_id] = task
        try:
            result = await task
            self._arrival_cache[stop_id] = result
            self._error_count, self._backoff_until = 0, None
            return result
        except Exception as err:
            cached = dict(self._arrival_cache.get(stop_id, {"arrivals": [], "next_minutes": None}))
            cached.update({"error": str(err), "stale": True})
            self._error_count += 1
            self._backoff_until = datetime.now(_TZ) + timedelta(seconds=min(MAX_BACKOFF, 2 ** min(self._error_count, 8)))
            _LOGGER.warning("EMT arrivals for stop %s failed: %s", stop_id, err)
            return cached
        finally:
            self._arrival_tasks.pop(stop_id, None)

    async def _fetch_arrivals(self, stop_id: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with async_get_clientsession(self.hass).get(
                        _BUS_TIMES_URL,
                        params={"parada": stop_id, "adaptados": "false"},
                        headers=_EMT_HEADERS,
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(f"EMT HTTP {response.status}")
                        return self._parse_arrivals(await response.text())
            except (ClientError, TimeoutError, ET.ParseError, RuntimeError) as err:
                last_error = err
                if attempt == 0:
                    await asyncio.sleep(1)
        raise RuntimeError(str(last_error or "Unknown EMT error"))

    @staticmethod
    def _scheduled_datetime(value: str, observed: datetime) -> str | None:
        try:
            values = [int(part) for part in value.split(":")]
            when = observed.replace(hour=values[0], minute=values[1], second=values[2] if len(values) == 3 else 0, microsecond=0)
            return (when + timedelta(days=1) if when < observed - timedelta(hours=6) else when).isoformat()
        except (ValueError, IndexError):
            return None

    def _parse_arrivals(self, body: str) -> dict[str, Any]:
        root = ET.fromstring(body)
        if root.tag != "estimacion":
            raise RuntimeError("Invalid EMT XML response")
        observed, observed_at = datetime.now(_TZ), datetime.now(_TZ).isoformat()
        arrivals: list[dict[str, Any]] = []
        for bus in root.findall(".//bus"):
            values = {child.tag: (child.text or "").strip() for child in bus}
            item: dict[str, Any] = {"line": values.get("linea"), "destination": values.get("destino"), "observed_at": observed_at}
            raw_minutes, raw_time, error = values.get("minutos", ""), values.get("horaLlegada", ""), values.get("error", "")
            match = re.match(r"^(\d+)\s*min\.?(?:utos)?$", raw_minutes, re.IGNORECASE)
            if error:
                item.update({"error": error, "time_type": "error"})
            elif match or raw_minutes.lower().startswith("pr") or raw_minutes.isdigit():
                minutes = int(match.group(1)) if match else (1 if raw_minutes.lower().startswith("pr") else int(raw_minutes))
                item.update({"minutes": minutes, "time_type": "estimated", "estimated_arrival": (observed + timedelta(minutes=minutes)).isoformat()})
            elif _CLOCK.match(raw_minutes) or _CLOCK.match(raw_time):
                arrival_time = raw_minutes if _CLOCK.match(raw_minutes) else raw_time
                item.update({"arrival_time": arrival_time, "time_type": "scheduled", "scheduled_arrival": self._scheduled_datetime(arrival_time, observed), "scheduled_date_inferred": True})
            else:
                item.update({"error": "No valid time data", "time_type": "error"})
            arrivals.append(item)
        valid_arrivals = [item for item in arrivals if item.get("time_type") in {"estimated", "scheduled"}]
        # EMT uses a 200 response for its own temporary-error page.  A parsed
        # XML document alone is therefore not a successful update.
        if arrivals and not valid_arrivals:
            errors = [str(item.get("error")) for item in arrivals if item.get("error")]
            raise RuntimeError(errors[0] if errors else "EMT returned no usable arrivals")
        arrivals.sort(key=lambda item: (0, item["minutes"]) if isinstance(item.get("minutes"), int) else ((0, item["scheduled_arrival"]) if item.get("scheduled_arrival") else (1, "")))
        minutes = [item["minutes"] for item in arrivals if isinstance(item.get("minutes"), int)]
        return {"arrivals": arrivals, "next_minutes": min(minutes) if minutes else None, "last_successful_update": observed_at, "stale": False}

    async def _async_update_data(self) -> dict[str, Any]:
        now, previous = datetime.now(_TZ), self.data or {}
        trackers: dict[str, Any] = {}
        stop_index: dict[str, dict[str, Any]] = {}
        refresh_stops: set[str] = set()
        # A deliberate button press is allowed to probe recovery immediately;
        # ordinary scheduled work observes the bounded backoff window.
        can_request = self._force_nearby or self._force_favorites or not self._backoff_until or now >= self._backoff_until
        for key in self.tracker_keys:
            entity_id, name = self._tracker_for_key(key)
            state, position = (self.hass.states.get(entity_id) if entity_id else None), None
            position = coords(state)
            prior = previous.get("trackers", {}).get(key, {})
            tracker: dict[str, Any] = {"entity_id": entity_id, "name": name, "nearby_stops": list(prior.get("nearby_stops", []))}
            if not position:
                tracker["error"] = "No valid GPS coordinates"
            elif not _in_emt_area(position):
                tracker.update({"location": {"latitude": position[0], "longitude": position[1]}, "nearby_stops": [], "error": "Outside EMT València coverage area"})
            else:
                interval = self.config[CONF_HOME_SCAN_INTERVAL] if state and state.state == "home" else self.config[CONF_AWAY_SCAN_INTERVAL]
                due = self._force_nearby or key not in self._nearby_due or (now - self._nearby_due[key]).total_seconds() >= interval
                if due and can_request:
                    try:
                        self._cache[key] = await self._nearby(*position)
                        self._locations[key], self._nearby_due[key] = position, now
                    except Exception as err:
                        tracker["error"] = f"Nearby stop lookup failed: {err}"
                cached = self._cache.get(key, tracker["nearby_stops"])
                tracker.update({"location": {"latitude": position[0], "longitude": position[1]}, "location_last_updated": state.last_updated.isoformat() if state else None, "presence": state.state if state else "unknown", "nearby_stops": [dict(item) for item in cached]})
                if due:
                    refresh_stops.update(item["stop_id"] for item in cached)
                for stop in cached:
                    stop_index[stop["stop_id"]] = stop
            trackers[key] = tracker
        favorite_defs = self.config[CONF_FAVORITE_STOPS]
        if can_request and any(str(item["stop_id"]) not in self._catalog and str(item["stop_id"]) not in stop_index for item in favorite_defs):
            await self._ensure_catalog()
        favorites: dict[str, dict[str, Any]] = {}
        for favorite in favorite_defs:
            stop_id = str(favorite["stop_id"])
            stop = dict(stop_index.get(stop_id) or self._catalog.get(stop_id) or {})
            alias, official = str(favorite.get("name") or "").strip(), stop.get("official_name") or stop.get("name")
            stop.update({"stop_id": stop_id, "name": alias or official or f"Parada {stop_id}", "custom_name": alias or None, "official_name": official})
            favorites[stop_id] = stop
            if self._force_favorites or stop_id not in self._favorite_due or (now - self._favorite_due[stop_id]).total_seconds() >= self.config[CONF_FAVORITES_SCAN_INTERVAL]:
                refresh_stops.add(stop_id)
        arrival_map: dict[str, dict[str, Any]] = {}
        for stop_id in set(stop_index) | set(favorites):
            if stop_id in refresh_stops and can_request:
                arrival_map[stop_id] = await self._arrivals(stop_id)
                if stop_id in favorites:
                    self._favorite_due[stop_id] = now
            else:
                arrival_map[stop_id] = dict(self._arrival_cache.get(stop_id, {}))
        for tracker in trackers.values():
            for stop in tracker["nearby_stops"]:
                stop.update(arrival_map.get(stop["stop_id"], {}))
        for stop_id, stop in favorites.items():
            stop.update(arrival_map.get(stop_id, {}))
        self._force_nearby = self._force_favorites = False
        last_success = max((item.get("last_successful_update") for item in arrival_map.values() if item.get("last_successful_update")), default=previous.get("last_successful_update"))
        return {"trackers": trackers, "favorites": favorites, "last_successful_update": last_success, "backoff_until": self._backoff_until.isoformat() if self._backoff_until else None}
