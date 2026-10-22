"""Aggregate sensors for selected GPS trackers and favourite EMT stops."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EMTValenciaConfigEntry
from .const import ATTR_ARRIVALS, ATTR_DISTANCE, ATTR_LAST_SUCCESS, ATTR_LOCATION, ATTR_NEARBY_STOPS, ATTR_STOP_ID, DOMAIN
from .coordinator import EMTValenciaDataUpdateCoordinator

ATTRIBUTION = "Data provided by EMT València"


async def async_setup_entry(hass: HomeAssistant, entry: EMTValenciaConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Create a bounded number of stable aggregate entities."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [EMTFavoriteStopsSensor(coordinator)]
    entities.extend(
        EMTTrackerSensor(coordinator, tracker) for tracker in coordinator.tracker_keys
    )
    entities.extend(EMTFavoriteSensor(coordinator, item["stop_id"]) for item in coordinator.config["favorite_stops"])
    async_add_entities(entities)


class _BaseSensor(CoordinatorEntity[EMTValenciaDataUpdateCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:bus-clock"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "min"

    async def async_update(self) -> None:
        """Support the standard Home Assistant manual Update action."""
        await self.coordinator.async_request_refresh()


class EMTTrackerSensor(_BaseSensor):
    _attr_name = "Paradas cercanas"

    def __init__(self, coordinator: EMTValenciaDataUpdateCoordinator, tracker_id: str) -> None:
        super().__init__(coordinator)
        self._tracker_id = tracker_id
        self._attr_unique_id = f"{DOMAIN}_tracker_{tracker_id}"
        _, name = coordinator._tracker_for_key(tracker_id)
        self._attr_device_info = {"identifiers": {(DOMAIN, f"tracker_{tracker_id}")}, "name": f"EMT València · {name}", "manufacturer": "EMT València", "model": "Nearby stops"}

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.data.get("trackers", {}).get(self._tracker_id, {})

    @property
    def native_value(self) -> int | None:
        values = [stop.get("next_minutes") for stop in self._data.get("nearby_stops", []) if isinstance(stop.get("next_minutes"), int)]
        return min(values) if values else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        return {ATTR_ATTRIBUTION: ATTRIBUTION, "device_tracker": self._tracker_id,
                ATTR_LOCATION: data.get("location"), "location_last_updated": data.get("location_last_updated"),
                ATTR_NEARBY_STOPS: data.get("nearby_stops", []), ATTR_LAST_SUCCESS: self.coordinator.data.get("last_successful_update"),
                "error": data.get("error")}


class EMTFavoriteStopsSensor(_BaseSensor):
    """Stable aggregate of every configured favourite stop."""

    # Keep the requested entity ID stable: sensor.emt_valencia_paradas_favoritas.
    _attr_has_entity_name = False
    _attr_name = "EMT València Paradas favoritas"
    _attr_icon = "mdi:bus-multiple"
    _attr_device_class = None
    _attr_native_unit_of_measurement = None

    def __init__(self, coordinator: EMTValenciaDataUpdateCoordinator) -> None:
        """Initialise the aggregate independently of the configured stops."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_favorite_stops"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "favorite_stops")},
            "name": "EMT València · favoritas",
            "manufacturer": "EMT València",
            "model": "Favourite stops aggregate",
        }

    @property
    def _data(self) -> dict[str, dict[str, Any]]:
        return self.coordinator.data.get("favorites", {})

    @property
    def native_value(self) -> int:
        return len(self._data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stops: list[dict[str, Any]] = []
        for stop in self._data.values():
            item = {
                "stop_id": stop["stop_id"],
                "name": stop.get("name"),
                ATTR_ARRIVALS: stop.get(ATTR_ARRIVALS, []),
                "next_minutes": stop.get("next_minutes"),
                "latitude": stop.get("latitude"),
                "longitude": stop.get("longitude"),
            }
            if stop.get("official_name"):
                item["official_name"] = stop["official_name"]
            if stop.get("custom_name"):
                item["custom_name"] = stop["custom_name"]
            if stop.get("error"):
                item["error"] = stop["error"]
            stops.append(item)
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "favorite_stops": stops,
            ATTR_LAST_SUCCESS: self.coordinator.data.get("last_successful_update"),
        }


class EMTFavoriteSensor(_BaseSensor):
    _attr_name = "Llegadas"

    def __init__(self, coordinator: EMTValenciaDataUpdateCoordinator, stop_id: str) -> None:
        super().__init__(coordinator)
        self._stop_id = str(stop_id)
        self._attr_unique_id = f"{DOMAIN}_favorite_{self._stop_id}"
        self._attr_device_info = {"identifiers": {(DOMAIN, f"favorite_{self._stop_id}")}, "name": f"EMT València · favorita {self._stop_id}", "manufacturer": "EMT València", "model": "Favourite stop"}

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.data.get("favorites", {}).get(self._stop_id, {})

    @property
    def native_value(self) -> int | None:
        value = self._data.get("next_minutes")
        return value if isinstance(value, int) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        return {ATTR_ATTRIBUTION: ATTRIBUTION, ATTR_STOP_ID: self._stop_id, "name": data.get("name"),
                "official_name": data.get("official_name"), "custom_name": data.get("custom_name"),
                "latitude": data.get("latitude"), "longitude": data.get("longitude"),
                ATTR_DISTANCE: data.get("distance_m"), "lines": data.get("lines", []), ATTR_ARRIVALS: data.get("arrivals", []),
                ATTR_LAST_SUCCESS: self.coordinator.data.get("last_successful_update"), "error": data.get("error")}
