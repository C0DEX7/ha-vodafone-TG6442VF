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
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": self.host,
            "Referer": f"{self.host}/index.html"
        }

    async def login(self) -> bool:
        """Attempt to authenticate by matching the router's exact session flow."""
        try:
            # Step 1: Hit the landing page first to establish a session cookie jar
            _LOGGER.debug("Initializing login session via gateway: %s", self.host)
            async with self.session.get(f"{self.host}/index.html", headers=self.headers, timeout=10) as response:
                await response.text()
                _LOGGER.debug("Initial handshake cookies obtained: %s", self.session.cookie_jar.filter_cookies(self.host))

            # Step 2: Attempt to pull a token data challenge if the firmware uses it
            # Some variants use /data/get_session.json or pass tokens in the body.
            # We'll post directly using the browser signature keys you uncovered.
            login_url = f"{self.host}/data/Login.json"
            
            # Since the browser uses an explicit runtime variable encryption layer 
            # for "EncryptData", we're going to try passing the raw credentials 
            # formatted matching the payload object schema.
            payload = {
                "AuthData": "loginPassword",
                "EncryptData": self.password,  # Sending token credentials
                "Name": self.username
            }

            _LOGGER.debug("Posting payload structure to %s", login_url)
            async with self.session.post(login_url, json=payload, headers=self.headers, timeout=10) as response:
                status = response.status
                raw_response = await response.text()
                _LOGGER.debug("Login endpoint response code: %s, Payload: %s", status, raw_response)
                
                if status == 200:
                    # Look inside response string for validation success markers
                    if "false" in raw_response.lower() or "error" in raw_response.lower() or "fail" in raw_response.lower():
                        _LOGGER.error("Credentials or dynamic encryption keys rejected by router chassis.")
                        return False
                    
                    _LOGGER.info("Integration successfully authorized access to Vodafone Station")
                    return True
                
                _LOGGER.error("Server endpoint returned unexpected error status: %s", status)
                return False

        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Chassis connection timed out or address wrong: %s", err)
            return False
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Unexpected runtime exception in client login: %s", err)
            return False

    async def async_get_data(self) -> dict:
        """Unified data state mapping container."""
        return {"sys_info": {"connected": True}, "devices": {}}

    async def async_close(self):
        """Close session pools safely."""
        if self.session:
            await self.session.close()
