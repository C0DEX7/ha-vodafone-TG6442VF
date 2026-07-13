"""Exposes direct action hooks to trigger physical device procedures."""
from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Expose system button controls for targeted operations."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.update_method.__self__
    
    async_add_entities([VodafoneStationRebootButton(coordinator, api)])

class VodafoneStationRebootButton(CoordinatorEntity, ButtonEntity):
    """Triggers an instantaneous hard reboot via the router API backend."""
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, coordinator, api):
        super().__init__(coordinator)
        self._api = api
        self._attr_name = "Vodafone Station Reboot"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_reboot"

    async def async_press(self) -> None:
        """Fire the reboot command execution payload."""
        await self._api.async_reboot()
