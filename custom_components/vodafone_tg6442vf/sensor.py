"""Exposes operational and DOCSIS connection health metrics to Home Assistant."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Construct entities tracking system diagnostics from coordinator states."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    sensors = [
        VodafoneStationSensor(coordinator, "Firmware Version", "sys_info", "firmware"),
        VodafoneStationSensor(coordinator, "WAN Status", "sys_info", "wan_status"),
        VodafoneStationSensor(coordinator, "WAN IP", "sys_info", "wan_ip"),
        VodafoneStationDiagnosticSensor(coordinator, "Downstream SNR", "docsis", "downstream_snr", "dB"),
        VodafoneStationDiagnosticSensor(coordinator, "Upstream Power", "docsis", "upstream_power", "dBmV"),
    ]
    async_add_entities(sensors)

class VodafoneStationSensor(CoordinatorEntity, SensorEntity):
    """Standard text/numeric monitoring state tracking."""
    
    def __init__(self, coordinator, name: str, category: str, key: str):
        super().__init__(coordinator)
        self._attr_name = f"Vodafone Station {name}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._category = category
        self._key = key

    @property
    def native_value(self):
        """Extract the exact live parameter string directly from the coordinator context."""
        return self.coordinator.data.get(self._category, {}).get(self._key, "Unknown")

class VodafoneStationDiagnosticSensor(VodafoneStationSensor):
    """Specialized hardware telemetry reporting channel."""
    
    def __init__(self, coordinator, name: str, category: str, key: str, unit: str):
        super().__init__(coordinator, name, category, key)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
