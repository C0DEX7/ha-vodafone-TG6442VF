"""API Client for Vodafone Station TG6442VF."""
import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)

class VodafoneStationAPI:
    """Handles communication with the Vodafone Station TG6442VF router."""

    def __init__(self, host: str, username: str, password: str, session: aiohttp.ClientSession = None):
        """Initialize the API client."""
        if not host.startswith(("http://", "https://")):
            self.host = f"http://{host}"
        else:
            self.host = host

        self.username = username
        self.password = password
        self.session = session or aiohttp.ClientSession()
        
        # Arris routers expect standard browser headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": self.host,
            "Referer": f"{self.host}/index.html"
        }

    async def login(self) -> bool:
        """Attempt to authenticate against the router's Arris backend."""
        try:
            _LOGGER.debug("Testing basic connectivity to gateway landing page: %s", self.host)
            async with self.session.get(f"{self.host}/index.html", headers=self.headers, timeout=10) as response:
                if response.status != 200:
                    _LOGGER.error("Router rejected baseline landing page request with status %s", response.status)
                    return False

            # The TG6442VF backend uses /data/Login.json for session validation
            login_url = f"{self.host}/data/Login.json"
            
            # Arris firmware typically maps login inputs using these specific keys
            payload = {
                "login_username": self.username,
                "login_password": self.password
            }

            _LOGGER.debug("Sending authentication payload to %s", login_url)
            
            # Sending as standard application/json POST
            async with self.session.post(login_url, json=payload, headers=self.headers, timeout=10) as response:
                _LOGGER.debug("Authentication endpoint response status: %s", response.status)
                
                if response.status == 200:
                    raw_text = await response.text()
                    _LOGGER.debug("Login raw response payload: %s", raw_text)
                    
                    # A 200 status doesn't always mean success if the password was wrong.
                    # The router might return a JSON body like {"result": "success"} or {"error": 0}
                    if "false" in raw_text.lower() or "error" in raw_text.lower():
                        _LOGGER.error("Router accepted the request but rejected the credentials.")
                        return False
                        
                    _LOGGER.info("Successfully authenticated with Vodafone Station TG6442VF")
                    return True
                
                _LOGGER.error("Authentication endpoint rejected connection with status code: %s", response.status)
                return False

        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Failed to establish a physical connection to the router: %s", err)
            return False
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Unexpected error during login execution: %s", err)
            return False

    async def async_get_data(self) -> dict:
        """Unified state and diagnostic framework placeholder."""
        # Clean execution path mapping for data loop coordinator
        return {
            "sys_info": {"firmware": "19.3B70-1.2.49", "wan_status": "Connected", "wan_ip": "10.0.0.1"},
            "wifi": {"2g_enabled": True, "5g_enabled": True, "guest_enabled": False},
            "docsis": {"downstream_snr": 38.2, "upstream_power": 44.5},
            "devices": {}
        }

    async def async_set_wifi_state(self, band: str, state: bool) -> bool:
        """Placeholder for radio state mutators."""
        return True

    async def async_reboot(self) -> bool:
        """Placeholder for systemic reboot triggers."""
        return True
