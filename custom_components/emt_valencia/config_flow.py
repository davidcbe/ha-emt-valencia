"""Config and options flows for EMT València."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_AWAY_SCAN_INTERVAL, CONF_FAVORITE_STOPS, CONF_FAVORITES_SCAN_INTERVAL,
    CONF_HOME_SCAN_INTERVAL, CONF_MAX_NEARBY_STOPS, CONF_MOBILE_DEVICES,
    CONF_MOVEMENT_THRESHOLD, CONF_SCAN_INTERVAL, CONF_SEARCH_RADIUS,
    DEFAULT_AWAY_SCAN_INTERVAL, DEFAULT_FAVORITES_SCAN_INTERVAL,
    DEFAULT_HOME_SCAN_INTERVAL, DEFAULT_MAX_NEARBY_STOPS, DEFAULT_MOVEMENT_THRESHOLD,
    DEFAULT_SEARCH_RADIUS, DOMAIN, MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL,
)

CONF_FAVORITE_STOP = "favorite_stop"
CONF_FAVORITE_ALIAS = "favorite_alias"


def _settings_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the general configuration form, without encoded favourite text."""
    return vol.Schema({
        vol.Optional(CONF_MOBILE_DEVICES, default=defaults.get(CONF_MOBILE_DEVICES, [])): selector.DeviceSelector(selector.DeviceSelectorConfig(integration="mobile_app", multiple=True)),
        vol.Optional(CONF_SEARCH_RADIUS, default=defaults.get(CONF_SEARCH_RADIUS, DEFAULT_SEARCH_RADIUS)): selector.NumberSelector(selector.NumberSelectorConfig(min=100, max=2000, step=50, unit_of_measurement="m")),
        vol.Optional(CONF_MAX_NEARBY_STOPS, default=defaults.get(CONF_MAX_NEARBY_STOPS, DEFAULT_MAX_NEARBY_STOPS)): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=10, step=1)),
        vol.Optional(CONF_HOME_SCAN_INTERVAL, default=defaults.get(CONF_HOME_SCAN_INTERVAL, DEFAULT_HOME_SCAN_INTERVAL)): selector.NumberSelector(selector.NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=30, unit_of_measurement="s")),
        vol.Optional(CONF_AWAY_SCAN_INTERVAL, default=defaults.get(CONF_AWAY_SCAN_INTERVAL, defaults.get(CONF_SCAN_INTERVAL, DEFAULT_AWAY_SCAN_INTERVAL))): selector.NumberSelector(selector.NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=30, unit_of_measurement="s")),
        vol.Optional(CONF_FAVORITES_SCAN_INTERVAL, default=defaults.get(CONF_FAVORITES_SCAN_INTERVAL, DEFAULT_FAVORITES_SCAN_INTERVAL)): selector.NumberSelector(selector.NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=30, unit_of_measurement="s")),
        vol.Optional(CONF_MOVEMENT_THRESHOLD, default=defaults.get(CONF_MOVEMENT_THRESHOLD, DEFAULT_MOVEMENT_THRESHOLD)): selector.NumberSelector(selector.NumberSelectorConfig(min=25, max=1000, step=25, unit_of_measurement="m")),
    })


def _normalize_settings(user_input: Mapping[str, Any], favorites: list[dict[str, str]]) -> dict[str, Any]:
    """Store settings and structured favourites without a user-facing syntax."""
    return {
        CONF_MOBILE_DEVICES: list(user_input.get(CONF_MOBILE_DEVICES, [])),
        CONF_FAVORITE_STOPS: favorites,
        CONF_SEARCH_RADIUS: int(user_input[CONF_SEARCH_RADIUS]),
        CONF_MAX_NEARBY_STOPS: int(user_input[CONF_MAX_NEARBY_STOPS]),
        CONF_SCAN_INTERVAL: int(user_input[CONF_AWAY_SCAN_INTERVAL]),
        CONF_HOME_SCAN_INTERVAL: int(user_input[CONF_HOME_SCAN_INTERVAL]),
        CONF_AWAY_SCAN_INTERVAL: int(user_input[CONF_AWAY_SCAN_INTERVAL]),
        CONF_FAVORITES_SCAN_INTERVAL: int(user_input[CONF_FAVORITES_SCAN_INTERVAL]),
        CONF_MOVEMENT_THRESHOLD: int(user_input[CONF_MOVEMENT_THRESHOLD]),
    }


class EMTValenciaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Set general settings; favourites are managed from Options afterwards."""
        if user_input is not None:
            return self.async_create_entry(title="EMT València", data=_normalize_settings(user_input, []))
        return self.async_show_form(step_id="user", data_schema=_settings_schema({}))

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> EMTValenciaOptionsFlow:
        return EMTValenciaOptionsFlow(config_entry)


class EMTValenciaOptionsFlow(config_entries.OptionsFlow):
    """Manage settings and favourites using structured, separate fields."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._settings = dict(config_entry.data)
        self._settings.update(config_entry.options)
        self._favorites = [dict(item) for item in self._settings.get(CONF_FAVORITE_STOPS, [])]
        self._edit_stop_id: str | None = None

    async def _stop_choices(self, favorites_only: bool = False) -> list[dict[str, str]]:
        """Use the coordinator catalogue, shared with normal EMT lookups."""
        catalog = await self._entry.runtime_data.async_get_stop_catalog()
        if favorites_only:
            ids = {str(item["stop_id"]) for item in self._favorites}
            catalog = [item for item in catalog if str(item["stop_id"]) in ids]
        return [{"value": str(item["stop_id"]), "label": f"{item['name']} · {item['stop_id']}"} for item in sorted(catalog, key=lambda item: (str(item["name"]).casefold(), str(item["stop_id"])))]

    def _finish(self) -> FlowResult:
        return self.async_create_entry(title="", data=_normalize_settings(self._settings, self._favorites))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(step_id="init", menu_options=["general", "favorites", "finish"])

    async def async_step_general(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._settings.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="general", data_schema=_settings_schema(self._settings))

    async def async_step_favorites(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        options = ["add_favorite"]
        if self._favorites:
            options.extend(["edit_favorite", "remove_favorite"])
        options.append("finish")
        return self.async_show_menu(step_id="favorites", menu_options=options)

    async def async_step_add_favorite(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        choices = await self._stop_choices()
        if not choices:
            return self.async_show_form(step_id="add_favorite", data_schema=vol.Schema({}), errors={"base": "catalog_unavailable"})
        errors: dict[str, str] = {}
        if user_input is not None:
            stop_id = str(user_input[CONF_FAVORITE_STOP])
            if any(str(item["stop_id"]) == stop_id for item in self._favorites):
                errors[CONF_FAVORITE_STOP] = "already_favorite"
            else:
                self._favorites.append({"stop_id": stop_id, "name": str(user_input.get(CONF_FAVORITE_ALIAS, "")).strip()})
                return await self.async_step_favorites()
        return self.async_show_form(step_id="add_favorite", data_schema=vol.Schema({
            vol.Required(CONF_FAVORITE_STOP): selector.SelectSelector(selector.SelectSelectorConfig(options=choices, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_FAVORITE_ALIAS, default=""): selector.TextSelector(),
        }), errors=errors)

    async def async_step_edit_favorite(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._edit_stop_id = str(user_input[CONF_FAVORITE_STOP])
            return await self.async_step_edit_alias()
        return self.async_show_form(step_id="edit_favorite", data_schema=vol.Schema({
            vol.Required(CONF_FAVORITE_STOP): selector.SelectSelector(selector.SelectSelectorConfig(options=await self._stop_choices(True), mode=selector.SelectSelectorMode.DROPDOWN)),
        }))

    async def async_step_edit_alias(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        favorite = next(item for item in self._favorites if str(item["stop_id"]) == self._edit_stop_id)
        if user_input is not None:
            favorite["name"] = str(user_input.get(CONF_FAVORITE_ALIAS, "")).strip()
            return await self.async_step_favorites()
        return self.async_show_form(step_id="edit_alias", data_schema=vol.Schema({
            vol.Optional(CONF_FAVORITE_ALIAS, default=favorite.get("name", "")): selector.TextSelector(),
        }))

    async def async_step_remove_favorite(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            stop_id = str(user_input[CONF_FAVORITE_STOP])
            self._favorites = [item for item in self._favorites if str(item["stop_id"]) != stop_id]
            return await self.async_step_favorites()
        return self.async_show_form(step_id="remove_favorite", data_schema=vol.Schema({
            vol.Required(CONF_FAVORITE_STOP): selector.SelectSelector(selector.SelectSelectorConfig(options=await self._stop_choices(True), mode=selector.SelectSelectorMode.DROPDOWN)),
        }))

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self._finish()
