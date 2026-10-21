"""Config flow for EMT València."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_STOP_ID, DEFAULT_STOP_ID, DOMAIN


class EMTValenciaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration through the Home Assistant UI."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Ask for the EMT stop number."""
        errors: dict[str, str] = {}

        if user_input is not None:
            stop_id = user_input[CONF_STOP_ID].strip()
            if stop_id.isdigit():
                await self.async_set_unique_id(stop_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"EMT València · parada {stop_id}",
                    data={CONF_STOP_ID: stop_id},
                )
            errors[CONF_STOP_ID] = "invalid_stop_id"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_STOP_ID, default=DEFAULT_STOP_ID): str}
            ),
            errors=errors,
        )
