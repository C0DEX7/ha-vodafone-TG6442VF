"""API Client for Vodafone Station TG6442VF."""
import hashlib
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
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": self.host,
            "Referer": f"{self.host}/index.html"
        }

    async def login(self) -> bool:
        """Attempt to authenticate by hashing credentials matching the router footprint."""
        try:
            # 1. Generate the SHA-256 hash of the password to match your browser's footprint
            password_bytes = self.password.encode("utf-8")
            hashed_password = hashlib.sha256(password_bytes).hexdigest()
            
            # 2. Build the payload matching the exact case and structure you intercepted
            payload = {
                "AuthData": "loginPassword",
                "EncryptData": hashed_password,
                "Name": self.username
            }

            # Based on the AuthData structure, Arris/CommScope endpoints usually hit /data/Login.json 
            # or a root data processing endpoint. We will use the structured path.
            login_url = f"{self.host}/data/Login.json"
            
            _LOGGER.debug("Sending encrypted authentication payload to %s", login_url)
            
            async with self.session.post(login_url, json=payload, headers=self.headers, timeout=10) as response:
                _LOGGER.debug("Authentication endpoint response status: %s", response.status)
                
                if response.status == 200:
                    raw_text = await response.text()
                    _LOGGER.debug("Login raw response payload: %s", raw_text)
                    
                    if "false" in raw_text.lower() or "error" in raw_text.lower() or "fail" in raw_text.lower():
                        _LOGGER.error("Router rejected the encrypted credentials. Check your username/password.")
                        return False
                        
                    _LOGGER.info("Successfully authenticated with Vodafone Station TG6442VF via encryption handshake")
                    return True
                
                _LOGGER.error("Authentication endpoint failed with status code: %s", response.status)
                return False

        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Failed to establish a physical connection to the router: %s", err)
            return False
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Unexpected error during login execution: %s", err)
            return False

    async def async_get_data(self) -> dict:
        """Unified state framework placeholder."""
        return {
            "sys_info": {"firmware": "TG6442VF_v1.0", "wan_status": "Connected"},
            "devices": {}
        }

    async def async_close(self):
        """Close the session tracking framework safely."""
        if self.session:
            await self.session.close()
