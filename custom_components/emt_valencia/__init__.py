"""EMT València integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_FAVORITE_STOPS, CONF_STOP_ID, DOMAIN
from .coordinator import EMTValenciaDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]
EMTValenciaConfigEntry = ConfigEntry[EMTValenciaDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EMTValenciaConfigEntry) -> bool:
    """Set up EMT València from a config entry."""
    coordinator = EMTValenciaDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(coordinator.async_start())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EMTValenciaConfigEntry) -> bool:
    """Unload an EMT València config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: EMTValenciaConfigEntry) -> None:
    """Reload after an options-flow change so tracker listeners match it."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Preserve a 0.1 fixed stop as an editable 0.2 favourite."""
    if entry.version == 1:
        data = dict(entry.data)
        if CONF_STOP_ID in data:
            data[CONF_FAVORITE_STOPS] = [{"stop_id": str(data[CONF_STOP_ID]), "name": ""}]
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True
