"""Sensor platform for EMT València."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_ARRIVALS, ATTR_STOP_ID, CONF_STOP_ID, DOMAIN
from .coordinator import EMTValenciaDataUpdateCoordinator
from . import EMTValenciaConfigEntry

ATTRIBUTION = "Data provided by EMT València"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EMTValenciaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the arrivals sensor for an EMT stop."""
    async_add_entities([EMTValenciaArrivalsSensor(entry.runtime_data, entry)])


class EMTValenciaArrivalsSensor(
    CoordinatorEntity[EMTValenciaDataUpdateCoordinator], SensorEntity
):
    """Represent the soonest live arrival for a configured stop."""

    _attr_has_entity_name = True
    _attr_name = "Próxima llegada"
    _attr_icon = "mdi:bus-clock"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "min"

    def __init__(
        self, coordinator: EMTValenciaDataUpdateCoordinator, entry: EMTValenciaConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._stop_id = entry.data[CONF_STOP_ID]
        self._attr_unique_id = f"{DOMAIN}_{self._stop_id}_next_arrival"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._stop_id)},
            "name": f"EMT València · parada {self._stop_id}",
            "manufacturer": "EMT València",
            "model": "Live arrivals",
        }

    @property
    def native_value(self) -> int | None:
        """Return the earliest valid minute-based prediction."""
        minutes = [
            arrival["minutos"]
            for arrival in self.coordinator.data
            if isinstance(arrival.get("minutos"), int)
        ]
        return min(minutes) if minutes else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all raw, display-ready arrivals from EMT."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            ATTR_STOP_ID: self._stop_id,
            ATTR_ARRIVALS: self.coordinator.data,
        }
