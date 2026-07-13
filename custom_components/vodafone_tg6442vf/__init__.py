"""Sets up coordinated local polling loops and maps platform spaces."""
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD, UPDATE_INTERVAL
from .router_api import VodafoneStationAPI

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "device_tracker", "switch", "button"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Establish state engine entries using a single explicit timing coordinator."""
    session = async_get_clientsession(hass)
    api = VodafoneStationAPI(
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session
    )

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=api.async_get_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )

    # Ensure initial state fetch finishes before completing integration startup
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down platforms and context links when removed by the user."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
