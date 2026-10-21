"""EMT València integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_STOP_ID, DOMAIN
from .coordinator import EMTValenciaDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]
EMTValenciaConfigEntry = ConfigEntry[EMTValenciaDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EMTValenciaConfigEntry) -> bool:
    """Set up EMT València from a config entry."""
    coordinator = EMTValenciaDataUpdateCoordinator(
        hass, entry.data[CONF_STOP_ID]
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EMTValenciaConfigEntry) -> bool:
    """Unload an EMT València config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok
