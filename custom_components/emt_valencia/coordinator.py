"""Data coordination for EMT València."""

from __future__ import annotations

import logging
from typing import Any

import emtvlcapi

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class EMTValenciaDataUpdateCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Fetch a stop's live arrivals once for all entities in an entry."""

    def __init__(self, hass: HomeAssistant, stop_id: str) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN} {stop_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.stop_id = stop_id

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch arrivals without blocking Home Assistant's event loop."""
        try:
            arrivals = await self.hass.async_add_executor_job(
                emtvlcapi.get_bus_times, self.stop_id
            )
        except Exception as err:
            raise UpdateFailed(f"Error retrieving EMT arrivals for {self.stop_id}: {err}") from err

        if not isinstance(arrivals, list):
            raise UpdateFailed("Unexpected response from EMT València")
        return arrivals
