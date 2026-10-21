"""Config and options flows for EMT València."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_TRACKERS, CONF_FAVORITE_STOPS, CONF_MAX_NEARBY_STOPS,
    CONF_MOVEMENT_THRESHOLD, CONF_SCAN_INTERVAL, CONF_SEARCH_RADIUS,
    DEFAULT_MAX_NEARBY_STOPS, DEFAULT_MOVEMENT_THRESHOLD,
    DEFAULT_SEARCH_RADIUS, DOMAIN, MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL,
)


def _parse_favorites(value: str) -> list[dict[str, str]]:
    """Parse ``1585:Casa, 1622:Trabajo`` from the UI."""
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value.split(","):
        stop_id, _, name = item.strip().partition(":")
        stop_id = stop_id.strip()
        if not stop_id:
            continue
        if not stop_id.isdigit():
            raise ValueError
        if stop_id not in seen:
            result.append({"stop_id": stop_id, "name": name.strip()})
            seen.add(stop_id)
    return result


def _favorite_text(stops: list[dict[str, str]]) -> str:
    return ", ".join(f"{item['stop_id']}:{item['name']}".rstrip(":") for item in stops)


def _schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the same UI form for setup and later options."""
    return vol.Schema({
        vol.Optional(CONF_DEVICE_TRACKERS, default=defaults.get(CONF_DEVICE_TRACKERS, [])):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="device_tracker", multiple=True)),
        vol.Optional(CONF_FAVORITE_STOPS, default=_favorite_text(defaults.get(CONF_FAVORITE_STOPS, []))):
            selector.TextSelector(),
        vol.Optional(CONF_SEARCH_RADIUS, default=defaults.get(CONF_SEARCH_RADIUS, DEFAULT_SEARCH_RADIUS)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=100, max=2000, step=50, unit_of_measurement="m")),
        vol.Optional(CONF_MAX_NEARBY_STOPS, default=defaults.get(CONF_MAX_NEARBY_STOPS, DEFAULT_MAX_NEARBY_STOPS)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=10, step=1)),
        vol.Optional(CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, MIN_SCAN_INTERVAL)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=30, unit_of_measurement="s")),
        vol.Optional(CONF_MOVEMENT_THRESHOLD, default=defaults.get(CONF_MOVEMENT_THRESHOLD, DEFAULT_MOVEMENT_THRESHOLD)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=25, max=1000, step=25, unit_of_measurement="m")),
    })


def _normalize(user_input: Mapping[str, Any]) -> dict[str, Any]:
    return {
        CONF_DEVICE_TRACKERS: list(user_input.get(CONF_DEVICE_TRACKERS, [])),
        CONF_FAVORITE_STOPS: _parse_favorites(str(user_input.get(CONF_FAVORITE_STOPS, ""))),
        CONF_SEARCH_RADIUS: int(user_input[CONF_SEARCH_RADIUS]),
        CONF_MAX_NEARBY_STOPS: int(user_input[CONF_MAX_NEARBY_STOPS]),
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
        CONF_MOVEMENT_THRESHOLD: int(user_input[CONF_MOVEMENT_THRESHOLD]),
    }


class EMTValenciaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                return self.async_create_entry(title="EMT València", data=_normalize(user_input))
            except ValueError:
                errors[CONF_FAVORITE_STOPS] = "invalid_favorites"
        return self.async_show_form(step_id="user", data_schema=_schema({}), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> EMTValenciaOptionsFlow:
        return EMTValenciaOptionsFlow(config_entry)


class EMTValenciaOptionsFlow(config_entries.OptionsFlow):
    """Edit mobile trackers, favourites and polling without reinstalling."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                return self.async_create_entry(title="", data=_normalize(user_input))
            except ValueError:
                errors[CONF_FAVORITE_STOPS] = "invalid_favorites"
        defaults = dict(self._entry.data)
        defaults.update(self._entry.options)
        return self.async_show_form(step_id="init", data_schema=_schema(defaults), errors=errors)
