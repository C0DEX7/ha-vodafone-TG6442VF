"""API Client for the Vodafone Station Wi-Fi 6 (TG6442VF) with Compal/Arris Firmware."""
import logging
import asyncio
import random
from typing import Any, Dict, Optional
from aiohttp import ClientSession

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

_LOGGER = logging.getLogger(__name__)

class VodafoneStationAPI:
    """Interface to communicate with the Vodafone Station TG6442VF router."""

    def __init__(self, host: str, username: str, password: str, session: ClientSession):
        """Initialize the API client."""
        self.host = host
        self.username = username
        self.password = password
        self.session = session

    async def _fetch_php_endpoint(self, endpoint_name: str) -> Optional[Any]:
        """
        Fetch data from a PHP AJAX endpoint.
        Handles minor underscore variations to prevent future firmware updates from breaking things.
        """
        n_val = random.randint(10000, 99999)
        variations = [
            f"php/{endpoint_name}.php",
        ]
        if "_" in endpoint_name:
            variations.append(f"php/{endpoint_name.replace('_', '')}.php")

        for path in variations:
            url = f"http://{self.host}/{path}?_n={n_val}"
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        try:
                            return await response.json()
                        except Exception:
                            # Some endpoints might return raw text or HTML on error
                            text = await response.text()
                            _LOGGER.debug("Non-JSON response from %s: %s", url, text[:200])
                            return text
            except Exception as err:
                _LOGGER.debug("Failed to fetch path %s: %s", url, err)
        return None

    async def login(self) -> bool:
        """Authenticate with the router using RSA-encrypted credentials."""
        _LOGGER.debug("Attempting login sequence with Vodafone Station at %s", self.host)

        # Step 1: Fetch the RSA Public Key Certificate
        cert_data = await self._fetch_php_endpoint("ajaxGet_Cert")
        if not cert_data or not isinstance(cert_data, dict) or "cert" not in cert_data:
            _LOGGER.error("Failed to retrieve RSA encryption certificate from router. Ensure you are connected to the router network.")
            return False

        cert_pem = cert_data["cert"]

        # Step 2: Encrypt password using the RSA Public Key with PKCS1v15 padding
        try:
            public_key = serialization.load_pem_public_key(cert_pem.encode('utf-8'))
            encrypted_bytes = public_key.encrypt(
                self.password.encode('utf-8'),
                padding.PKCS1v15()
            )
            encrypt_data = encrypted_bytes.hex()
        except Exception as err:
            _LOGGER.error("Failed to encrypt password using retrieved certificate: %s", err)
            return False

        # Step 3: POST the payload to the login handler
        n_val = random.randint(10000, 99999)
        login_url = f"http://{self.host}/php/ajaxSet_Password.php?_n={n_val}"
        
        # This firmware expects x-www-form-urlencoded format
        payload = {
            "AuthData": "loginPassword",
            "EncryptData": encrypt_data,
            "Name": self.username
        }

        try:
            async with self.session.post(login_url, data=payload) as response:
                response.raise_for_status()
                resp_text = await response.text()
                _LOGGER.debug("Login response: %s", resp_text)

                # A successful login request validates the current cookie session in aiohttp
                if "success" in resp_text.lower() or "ok" in resp_text.lower() or response.status == 200:
                    _LOGGER.info("Successfully authenticated with Vodafone Station.")
                    return True
        except Exception as err:
            _LOGGER.error("Network error during login post: %s", err)

        return False

    async def async_get_data(self) -> Dict[str, Any]:
        """Fetch and compile all router data for Home Assistant."""
        # Check authentication by attempting to fetch basic system info
        sys_resp = await self._fetch_php_endpoint("ajaxGet_System_Info")
        if sys_resp is None or (isinstance(sys_resp, str) and "login" in sys_resp.lower()):
            _LOGGER.debug("Session expired or unauthenticated. Logging in...")
            if not await self.login():
                raise Exception("Authentication with Vodafone Station failed.")
            sys_resp = await self._fetch_php_endpoint("ajaxGet_System_Info")

        # Concurrently fetch other data sets to maximize responsiveness
        tasks = [
            self._fetch_php_endpoint("ajaxGet_DocsisStatus"),
            self._fetch_php_endpoint("ajaxGet_WifiSettings"),
            self._fetch_php_endpoint("ajaxGet_LanUserList")
        ]
        docsis_resp, wifi_resp, devices_resp = await asyncio.gather(*tasks)

        # --- 1. Parse System Info ---
        firmware = "Unknown"
        wan_status = "Disconnected"
        wan_ip = "0.0.0.0"
        if isinstance(sys_resp, dict):
            firmware = sys_resp.get("sys_firmware") or sys_resp.get("firmware_version") or "Unknown"
            wan_status = sys_resp.get("sys_wan_status") or sys_resp.get("wan_status") or "Unknown"
            wan_ip = sys_resp.get("sys_wan_ip") or sys_resp.get("wan_ip") or "0.0.0.0"

        # --- 2. Parse DOCSIS telemetry ---
        downstream_snr = 0.0
        upstream_power = 0.0
        if isinstance(docsis_resp, dict):
            # Safe extraction from lists (taking the first channel's value)
            ds_channels = docsis_resp.get("downstream") or docsis_resp.get("ds_channels") or []
            if ds_channels and isinstance(ds_channels, list) and isinstance(ds_channels[0], dict):
                downstream_snr = float(ds_channels[0].get("snr") or ds_channels[0].get("SNR") or 0.0)

            us_channels = docsis_resp.get("upstream") or docsis_resp.get("us_channels") or []
            if us_channels and isinstance(us_channels, list) and isinstance(us_channels[0], dict):
                upstream_power = float(us_channels[0].get("power") or us_channels[0].get("Power") or 0.0)

        # --- 3. Parse Wi-Fi Radio Settings ---
        wifi_data = {
            "2g_enabled": False,
            "5g_enabled": False,
            "guest_enabled": False
        }
        if isinstance(wifi_resp, dict):
            for k, v in wifi_resp.items():
                val = str(v).lower() in ["1", "true", "yes", "on", "enable", "enabled"]
                k_lower = k.lower()
                if "24" in k_lower or "2g" in k_lower or "radio_2" in k_lower:
                    wifi_data["2g_enabled"] = val
                elif "5" in k_lower or "5g" in k_lower or "radio_5" in k_lower:
                    wifi_data["5g_enabled"] = val
                elif "guest" in k_lower:
                    wifi_data["guest_enabled"] = val

        # --- 4. Parse Client Devices list ---
        devices_data = self._parse_devices(devices_resp)

        return {
            "sys_info": {
                "firmware": firmware,
                "wan_status": wan_status,
                "wan_ip": wan_ip,
            },
            "docsis": {
                "downstream_snr": downstream_snr,
                "upstream_power": upstream_power,
            },
            "wifi": wifi_data,
            "devices": devices_data
        }

    def _parse_devices(self, raw_data: Any) -> Dict[str, Dict[str, Any]]:
        """Parse raw device tables into Home Assistant tracking dictionaries."""
        parsed = {}
        if not raw_data:
            return parsed

        client_list = []
        if isinstance(raw_data, list):
            client_list = raw_data
        elif isinstance(raw_data, dict):
            for key in ["lan_user_list", "clients", "devices", "list"]:
                if key in raw_data and isinstance(raw_data[key], list):
                    client_list = raw_data[key]
                    break

        for client in client_list:
            if not isinstance(client, dict):
                continue

            mac = None
            for mac_key in ["MACAddr", "mac", "mac_address", "Mac"]:
                if mac_key in client:
                    mac = client[mac_key]
                    break

            if not mac:
                continue

            name = None
            for name_key in ["DeviceName", "hostname", "name", "HostName"]:
                if name_key in client:
                    name = client[name_key]
                    break
            if not name:
                name = f"Device_{mac[-8:].replace(':', '')}"

            connected = False
            for conn_key in ["Online", "active", "connected", "state"]:
                if conn_key in client:
                    val = client[conn_key]
                    if str(val).lower() in ["1", "true", "yes", "online", "up"]:
                        connected = True
                    break

            parsed[mac] = {
                "name": name,
                "connected": connected
            }
        return parsed

    async def async_reboot(self) -> None:
        """Trigger a reboot request to the router."""
        _LOGGER.info("Initiating Vodafone Station reboot sequence.")
        n_val = random.randint(10000, 99999)
        url = f"http://{self.host}/php/ajaxSet_Reboot.php?_n={n_val}"
        payload = {"action": "reboot", "reboot": "1"}
        try:
            async with self.session.post(url, data=payload) as response:
                if response.status == 200:
                    _LOGGER.info("Reboot command acknowledged by router.")
                else:
                    _LOGGER.warning("Reboot endpoint rejected signal with status: %s", response.status)
        except Exception as err:
            _LOGGER.error("Failed to execute reboot: %s", err)

    async def async_set_wifi_state(self, band: str, state: bool) -> bool:
        """Enable or disable target Wi-Fi radios."""
        _LOGGER.info("Setting Wi-Fi band %s state to %s", band, state)
        n_val = random.randint(10000, 99999)
        url = f"http://{self.host}/php/ajaxSet_WifiSettings.php?_n={n_val}"
        
        val_str = "1" if state else "0"
        payload = {}
        if band == "2g":
            payload = {"wifi_24g_enable": val_str}
        elif band == "5g":
            payload = {"wifi_5g_enable": val_str}
        elif band == "guest":
            payload = {"wifi_guest_enable": val_str}

        try:
            async with self.session.post(url, data=payload) as response:
                if response.status == 200:
                    _LOGGER.info("Wi-Fi configuration successfully updated.")
                    return True
        except Exception as err:
            _LOGGER.error("Failed to commit Wi-Fi state alteration: %s", err)
        return False
