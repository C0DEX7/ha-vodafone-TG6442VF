"""Maps active MAC addresses to provide local network presence detection."""
import logging
from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Dynamically register tracking endpoints for known MAC addresses."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices = coordinator.data.get("devices", {})
    
    entities = [VodafoneStationDeviceTracker(coordinator, mac) for mac in devices]
    async_add_entities(entities)

class VodafoneStationDeviceTracker(CoordinatorEntity, ScannerEntity):
    """Presence entity driven entirely by shared local coordinator states."""

    def __init__(self, coordinator, mac: str):
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"vodafone_tracker_{mac}"

    @property
    def name(self) -> str:
        device_entry = self.coordinator.data.get("devices", {}).get(self._mac, {})
        return device_entry.get("name", f"Device {self._mac}")

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        device_entry = self.coordinator.data.get("devices", {}).get(self._mac, {})
        return device_entry.get("connected", False)
