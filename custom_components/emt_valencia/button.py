"""Manual refresh buttons for EMT València."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EMTValenciaConfigEntry
from .const import DOMAIN
from .coordinator import EMTValenciaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: EMTValenciaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Expose actions that use the coordinator's shared request lock."""
    coordinator = entry.runtime_data
    async_add_entities([
        EMTRefreshButton(coordinator, "favorites", "Actualizar favoritas", "mdi:star-refresh"),
        EMTRefreshButton(coordinator, "nearby", "Actualizar paradas cercanas", "mdi:map-marker-radius"),
        EMTRefreshButton(coordinator, "all", "Actualizar EMT", "mdi:refresh"),
    ])


class EMTRefreshButton(CoordinatorEntity[EMTValenciaDataUpdateCoordinator], ButtonEntity):
    """Request one immediate refresh without issuing a duplicate request."""

    _attr_has_entity_name = False

    def __init__(self, coordinator: EMTValenciaDataUpdateCoordinator, action: str, name: str, icon: str) -> None:
        super().__init__(coordinator)
        self._action = action
        self._attr_name = f"EMT València {name}"
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}_refresh_{action}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "controls")},
            "name": "EMT València · controles",
            "manufacturer": "EMT València",
            "model": "Refresh controls",
        }

    async def async_press(self) -> None:
        if self._action == "favorites":
            await self.coordinator.async_refresh_favorites()
        elif self._action == "nearby":
            await self.coordinator.async_refresh_nearby()
        else:
            await self.coordinator.async_refresh_all()
