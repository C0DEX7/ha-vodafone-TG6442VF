"""Provides entity platforms to activate or deactivate Wi-Fi radio configurations."""
from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Map switch controllers directly to physical hardware toggles."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.update_method.__self__
    
    switches = [
        VodafoneStationWifiSwitch(coordinator, api, "2.4 GHz Wi-Fi", "2g_enabled", "2g"),
        VodafoneStationWifiSwitch(coordinator, api, "5 GHz Wi-Fi", "5g_enabled", "5g"),
        VodafoneStationWifiSwitch(coordinator, api, "Guest Wi-Fi", "guest_enabled", "guest"),
    ]
    async_add_entities(switches)

class VodafoneStationWifiSwitch(CoordinatorEntity, SwitchEntity):
    """Switch control wrapper targeting specific router configurations."""

    def __init__(self, coordinator, api, name: str, data_key: str, api_band: str):
        super().__init__(coordinator)
        self._api = api
        self._attr_name = f"Vodafone Station {name}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{data_key}"
        self._attr_icon = "mdi:wifi"
        self._data_key = data_key
        self._api_band = api_band

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("wifi", {}).get(self._data_key, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Commit an activation command to the target radio interface."""
        if await self._api.async_set_wifi_state(self._api_band, True):
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Commit a deactivation command to the target radio interface."""
        if await self._api.async_set_wifi_state(self._api_band, False):
            await self.coordinator.async_request_refresh()
