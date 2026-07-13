"""Handles user-facing interactive configuration setup within the UI."""
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from .router_api import VodafoneStationAPI

class VodafoneStationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Manage integration discovery and onboarding UI flows."""
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle onboarding parameters supplied via user input forms."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = VodafoneStationAPI(
                user_input[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                session
            )
            
            if await api.login():
                return self.async_create_entry(
                    title=f"Vodafone Station ({user_input[CONF_HOST]})", 
                    data=user_input
                )
            
            errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required(CONF_HOST, default="192.168.0.1"): str,
            vol.Required(CONF_USERNAME, default="admin"): str,
            vol.Required(CONF_PASSWORD): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
