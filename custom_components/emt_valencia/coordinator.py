"""Polling, GPS lookup and request de-duplication for EMT València."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from math import asin, cos, radians, sin, sqrt
from typing import Any

import emtvlcapi
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_TRACKERS, CONF_FAVORITE_STOPS, CONF_MAX_NEARBY_STOPS, CONF_MOBILE_DEVICES,
    CONF_MOVEMENT_THRESHOLD, CONF_SCAN_INTERVAL, CONF_SEARCH_RADIUS, CONF_STOP_ID,
    DEFAULT_MAX_NEARBY_STOPS, DEFAULT_MOVEMENT_THRESHOLD, DEFAULT_SCAN_INTERVAL,
    DEFAULT_SEARCH_RADIUS, DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def distance_m(a: float, b: float, c: float, d: float) -> int:
    """Great-circle distance in metres."""
    x, y = radians(c - a), radians(d - b)
    h = sin(x / 2) ** 2 + cos(radians(a)) * cos(radians(c)) * sin(y / 2) ** 2
    return round(6_371_000 * 2 * asin(sqrt(h)))


def coords(state: Any) -> tuple[float, float] | None:
    if state is None or state.state in {"unknown", "unavailable"}:
        return None
    try:
        latitude, longitude = float(state.attributes["latitude"]), float(state.attributes["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    return (latitude, longitude) if -90 <= latitude <= 90 and -180 <= longitude <= 180 else None


class EMTValenciaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One shared updater; cached stop searches, live arrivals every refresh."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry, self._cache, self._locations, self._unsub = entry, {}, {}, None
        super().__init__(hass, logger=_LOGGER, name=DOMAIN, update_interval=DEFAULT_SCAN_INTERVAL)
        self.update_interval = timedelta(seconds=self.config[CONF_SCAN_INTERVAL])

    @property
    def config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            CONF_DEVICE_TRACKERS: [], CONF_MOBILE_DEVICES: [], CONF_FAVORITE_STOPS: [],
            CONF_SEARCH_RADIUS: DEFAULT_SEARCH_RADIUS,
            CONF_MAX_NEARBY_STOPS: DEFAULT_MAX_NEARBY_STOPS,
            CONF_SCAN_INTERVAL: int(DEFAULT_SCAN_INTERVAL.total_seconds()),
            CONF_MOVEMENT_THRESHOLD: DEFAULT_MOVEMENT_THRESHOLD,
        }
        config.update(self.entry.data)
        config.update(self.entry.options)
        # Existing 0.1 entries remain useful but can remove 1622 in Options.
        if CONF_STOP_ID in self.entry.data and not self.entry.options:
            config[CONF_FAVORITE_STOPS] = [{"stop_id": str(self.entry.data[CONF_STOP_ID]), "name": ""}]
        return config

    @property
    def tracker_keys(self) -> list[str]:
        """Return stable keys for configured Companion devices or legacy entities."""
        if CONF_MOBILE_DEVICES in self.entry.data or CONF_MOBILE_DEVICES in self.entry.options:
            return self.config[CONF_MOBILE_DEVICES]
        return self.config[CONF_DEVICE_TRACKERS]

    def _tracker_for_key(self, key: str) -> tuple[str | None, str]:
        """Resolve a Companion device to its usable GPS tracker.

        Older entries store an entity id directly and remain supported.
        """
        if key.startswith("device_tracker."):
            state = self.hass.states.get(key)
            return key, state.name if state else key
        device = dr.async_get(self.hass).async_get(key)
        name = (device.name_by_user or device.name) if device else key
        candidates = [entry.entity_id for entry in er.async_entries_for_device(er.async_get(self.hass), key)
                      if entry.domain == "device_tracker" and entry.platform == "mobile_app"]
        # Prefer the tracker that currently carries valid latitude/longitude.
        entity_id = next((item for item in candidates if coords(self.hass.states.get(item))), None)
        return entity_id or (candidates[0] if candidates else None), name

    def async_start(self) -> Any:
        entities = [entity_id for key in self.tracker_keys
                    if (entity_id := self._tracker_for_key(key)[0])]
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
        if new and old and distance_m(*old, *new) >= self.config[CONF_MOVEMENT_THRESHOLD]:
            self.async_request_refresh()

    async def _nearby(self, latitude: float, longitude: float) -> list[dict[str, Any]]:
        radius = self.config[CONF_SEARCH_RADIUS]
        lat_delta = radius / 111_320
        lon_delta = radius / max(1, 111_320 * cos(radians(latitude)))
        rows = await self.hass.async_add_executor_job(
            emtvlcapi.get_stops_in_extent, latitude-lat_delta, longitude-lon_delta,
            latitude+lat_delta, longitude+lon_delta)
        stops = []
        for row in rows:
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
                distance = distance_m(latitude, longitude, lat, lon)
            except (KeyError, TypeError, ValueError):
                continue
            if distance <= radius and row.get("stopId"):
                routes = row.get("routes", [])
                official_name = row.get("name") or row.get("ubica") or "Parada EMT"
                stops.append({"stop_id": str(row["stopId"]), "name": official_name,
                    "official_name": official_name,
                    "distance_m": distance, "latitude": lat, "longitude": lon,
                    "lines": [{"line": r.get("SN") or r.get("lineaNumber") or r.get("id_linea"),
                               "destination": r.get("headSign") or r.get("LN") or r.get("lineaName")} for r in routes]})
        return sorted(stops, key=lambda item: item["distance_m"])[:self.config[CONF_MAX_NEARBY_STOPS]]

    async def _arrivals(self, stop_id: str) -> dict[str, Any]:
        try:
            rows = await self.hass.async_add_executor_job(emtvlcapi.get_bus_times, stop_id)
        except Exception as err:
            return {"arrivals": [], "error": str(err)}
        arrivals = []
        for row in rows if isinstance(rows, list) else []:
            item = {"line": row.get("linea"), "destination": row.get("destino")}
            if isinstance(row.get("minutos"), int) and row["minutos"] >= 0:
                item["minutes"] = row["minutos"]
            elif row.get("horaLlegada"):
                item["arrival_time"] = row["horaLlegada"]
            else:
                item["error"] = row.get("error", "Invalid arrival response")
            arrivals.append(item)
        minutes = [item["minutes"] for item in arrivals if "minutes" in item]
        return {"arrivals": arrivals, "next_minutes": min(minutes) if minutes else None}

    async def _async_update_data(self) -> dict[str, Any]:
        trackers: dict[str, Any] = {}
        unique: dict[str, dict[str, Any]] = {}
        for key in self.tracker_keys:
            entity_id, name = self._tracker_for_key(key)
            state = self.hass.states.get(entity_id) if entity_id else None
            position = coords(state)
            tracker: dict[str, Any] = {"entity_id": entity_id, "name": name, "nearby_stops": []}
            if not position:
                tracker["error"] = "No valid GPS coordinates"
            else:
                old, cached = self._locations.get(key), self._cache.get(key)
                if cached is None or old is None or distance_m(*old, *position) >= self.config[CONF_MOVEMENT_THRESHOLD]:
                    try:
                        cached = await self._nearby(*position)
                    except Exception as err:
                        cached, tracker["error"] = [], f"Nearby stop lookup failed: {err}"
                    self._cache[key], self._locations[key] = cached, position
                tracker.update({"location": {"latitude": position[0], "longitude": position[1]},
                                "location_last_updated": state.last_updated.isoformat(), "nearby_stops": [dict(x) for x in cached]})
                for stop in cached:
                    unique[stop["stop_id"]] = stop
            trackers[key] = tracker
        favorites: dict[str, dict[str, Any]] = {}
        for favorite in self.config[CONF_FAVORITE_STOPS]:
            stop_id = str(favorite["stop_id"])
            stop = dict(unique.get(stop_id, {}))
            custom_name = str(favorite.get("name") or "").strip()
            official_name = stop.get("official_name") or stop.get("name")
            name = (
                f"{custom_name} · {official_name}"
                if custom_name and official_name and custom_name != official_name
                else custom_name or official_name or f"Parada {stop_id}"
            )
            stop.update({"stop_id": stop_id, "name": name,
                         "custom_name": custom_name or None,
                         "official_name": official_name})
            favorites[stop_id] = unique[stop_id] = stop
        results = await asyncio.gather(*(self._arrivals(stop_id) for stop_id in unique))
        arrival_map = dict(zip(unique, results, strict=True))
        for tracker in trackers.values():
            for stop in tracker["nearby_stops"]:
                stop.update(arrival_map.get(stop["stop_id"], {}))
        for stop_id, stop in favorites.items():
            stop.update(arrival_map.get(stop_id, {}))
        return {"trackers": trackers, "favorites": favorites,
                "last_successful_update": datetime.now().astimezone().isoformat()}
