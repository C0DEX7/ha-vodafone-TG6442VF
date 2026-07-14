"""API Client for the Vodafone Station Wi-Fi 6 (TG6442VF)."""
import logging
import asyncio
from typing import Any, Dict, Optional
from aiohttp import ClientSession, ClientError

_LOGGER = logging.getLogger(__name__)

class VodafoneStationAPI:
    """Interface to communicate with the Vodafone Station TG6442VF router."""

    def __init__(self, host: str, username: str, password: str, session: ClientSession):
        """Initialize the API client."""
        self.host = host
        self.username = username
        self.password = password
        self.session = session
        self.base_url = f"http://{host}/api/v1"  # Adjust if your firmware uses a different base API path
        self._token: Optional[str] = None

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Internal helper to execute HTTP requests with error handling."""
        url = f"{self.base_url}/{endpoint}"
        
        # Inject auth token into headers if we have one
        headers = kwargs.get("headers", {})
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
            # Some Vodafone/Arris firmwares use a custom CSRF header instead:
            # headers["X-CSRF-TOKEN"] = self._token
        kwargs["headers"] = headers

        try:
            async with self.session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                # Assuming the router returns JSON. If it returns XML or raw HTML, 
                # you'll need to parse response.text() instead.
                return await response.json()
        except ClientError as err:
            _LOGGER.error("Connection error communicating with Vodafone Station at %s: %s", url, err)
        except Exception as err:
            _LOGGER.error("Unexpected error interacting with Vodafone Station API: %s", err)
            
        return None

    async def login(self) -> bool:
        """Authenticate with the router and obtain a session token."""
        _LOGGER.debug("Attempting to login to Vodafone Station at %s", self.host)
        
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        # Adjust the login endpoint and payload format according to your specific firmware
        response = await self._request("POST", "login", json=payload)
        
        if response and "token" in response:
            self._token = response["token"]
            return True
            
        _LOGGER.warning("Failed to authenticate with Vodafone Station. Invalid credentials or API changed.")
        return False

    async def async_get_data(self) -> Dict[str, Any]:
        """
        Fetch all required state data for the coordinator.
        Returns a dictionary mapped to the exact keys expected by the platforms.
        """
        if not self._token and not await self.login():
            raise Exception("Cannot fetch data: Authentication failed.")

        # In a real scenario, you might need to make multiple API calls here
        # For efficiency, we will execute them concurrently
        try:
            sys_resp, wifi_resp, devices_resp, docsis_resp = await asyncio.gather(
                self._request("GET", "system/info"),
                self._request("GET", "wifi/status"),
                self._request("GET", "network/devices"),
                self._request("GET", "docsis/status")
            )
        except Exception as err:
            _LOGGER.error("Error fetching data batch: %s", err)
            return {}

        # --- Data Mapping ---
        # You will need to map the raw JSON responses from your router
        # to the exact dictionary schema expected by your components.
        
        return {
            "sys_info": {
                "firmware": sys_resp.get("firmware_version", "Unknown") if sys_resp else "Unknown",
                "wan_status": sys_resp.get("wan_status", "Disconnected") if sys_resp else "Unknown",
                "wan_ip": sys_resp.get("wan_ip", "0.0.0.0") if sys_resp else "Unknown",
            },
            "docsis": {
                "downstream_snr": docsis_resp.get("downstream_snr", 0) if docsis_resp else 0,
                "upstream_power": docsis_resp.get("upstream_power", 0) if docsis_resp else 0,
            },
            "wifi": {
                "2g_enabled": wifi_resp.get("2g_active", False) if wifi_resp else False,
                "5g_enabled": wifi_resp.get("5g_active", False) if wifi_resp else False,
                "guest_enabled": wifi_resp.get("guest_active", False) if wifi_resp else False,
            },
            "devices": self._parse_devices(devices_resp)
        }

    def _parse_devices(self, raw_devices_data: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Helper to map router device lists to the tracker dictionary format."""
        parsed = {}
        if not raw_devices_data or "clients" not in raw_devices_data:
            return parsed
            
        # Expected output format: {"00:11:22:33:44:55": {"name": "iPhone", "connected": True}}
        for client in raw_devices_data["clients"]:
            mac = client.get("mac")
            if mac:
                parsed[mac] = {
                    "name": client.get("hostname", f"Unknown_{mac[-8:]}"),
                    "connected": client.get("active", False)
                }
        return parsed

    async def async_reboot(self) -> None:
        """Trigger a hardware reboot of the router."""
        if not self._token and not await self.login():
            _LOGGER.error("Cannot reboot: Authentication failed.")
            return
            
        _LOGGER.info("Initiating Vodafone Station reboot sequence.")
        # Usually requires a specific JSON payload or form data to confirm intent
        payload = {"action": "reboot", "confirm": True}
        await self._request("POST", "system/reboot", json=payload)

    async def async_set_wifi_state(self, band: str, state: bool) -> bool:
        """
        Enable or disable a specific Wi-Fi band.
        :param band: "2g", "5g", or "guest" (mapped from switch.py)
        :param state: True to turn on, False to turn off
        """
        if not self._token and not await self.login():
            _LOGGER.error("Cannot change Wi-Fi state: Authentication failed.")
            return False

        _LOGGER.debug("Setting Wi-Fi band %s to %s", band, state)
        
        # Map the internal band string to the router's expected API parameter
        api_band_map = {
            "2g": "radio_24",
            "5g": "radio_50",
            "guest": "radio_guest"
        }
        
        target_radio = api_band_map.get(band)
        if not target_radio:
            _LOGGER.error("Invalid Wi-Fi band requested: %s", band)
            return False

        payload = {
            "radio": target_radio,
            "enabled": state
        }
        
        response = await self._request("POST", "wifi/config", json=payload)
        
        # Return True if the router acknowledged the change successfully
        return bool(response and response.get("status") == "success")
