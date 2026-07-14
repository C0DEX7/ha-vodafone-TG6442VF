"""API client for the Vodafone Station TG6442VF (Sercomm-based firmware).

This router does NOT expose the newer `/api/v1/...` JSON API that some other
Vodafone Station models use. Instead, like other Sercomm-based Vodafone
Station units, it uses an older `/php/*.php` AJAX API with a session cookie
and a per-request cache-busting `_n` query parameter.

Login is a two-step dance:
    1. GET the login page to establish a session cookie (and, on some
       firmwares, read a nonce/salt embedded in the page or returned by a
       companion endpoint).
    2. POST the encrypted password to /php/ajaxSet_Password.php.

IMPORTANT - the `_encrypt_password` method below is a best-effort starting
point, not a confirmed implementation. Sercomm firmwares vary in exactly how
they transform the password client-side before it's sent as `EncryptData`.
If login still fails after wiring this up, open http://<router-ip>/login.html
in a browser, check the page source / Sources tab in devtools for the JS
function invoked right before the POST to ajaxSet_Password.php, and swap the
body of `_encrypt_password` for a faithful Python port of it.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

LOGIN_PAGE = "/login.html"
LOGIN_ENDPOINT = "/php/ajaxSet_Password.php"
REBOOT_ENDPOINT = "/php/ajaxSet_status_restart.php"
WIFI_ENDPOINT = "/php/ajaxSet_wifi.php"
DEVICES_ENDPOINT = "/php/ajaxGet_device_list.php"
SYSINFO_ENDPOINT = "/php/ajaxGet_status_docsis_data.php"

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)


class VodafoneStationAuthError(Exception):
    """Raised when login fails (bad credentials or unexpected response)."""


class VodafoneStationConnectionError(Exception):
    """Raised when the router can't be reached at all."""


def _cache_buster() -> str:
    """Router expects a changing _n query param on every AJAX call."""
    return str(int(time.time() * 1000))


class VodafoneStationAPI:
    """Thin async client around the TG6442VF's legacy PHP AJAX endpoints."""

    def __init__(self, host: str, username: str, password: str, session: aiohttp.ClientSession):
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._session = session
        self._base_url = f"http://{self._host}"
        self._logged_in = False

    def _encrypt_password(self, nonce: str) -> str:
        """Best-effort password transform — VERIFY against your router's login.js.

        Placeholder scheme: SHA-256(password + nonce), hex-encoded. Swap this
        out once you've confirmed the real client-side function from the
        router's own JavaScript (see module docstring).
        """
        digest = hashlib.sha256(f"{self._password}{nonce}".encode()).hexdigest()
        return digest

    async def _get_login_nonce(self) -> str:
        """Fetch the login page and establish the session cookie.

        Also tries to pull a nonce/salt out of the page if one is present.
        Falls back to an empty string if none is found — some firmwares
        don't require one and simply rely on the session cookie.
        """
        url = f"{self._base_url}{LOGIN_PAGE}"
        try:
            async with self._session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    raise VodafoneStationConnectionError(
                        f"Unexpected status {resp.status} loading {url}"
                    )
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise VodafoneStationConnectionError(
                f"Connection error communicating with Vodafone Station at {url}: {err}"
            ) from err

        # Common patterns for an embedded nonce/salt on Sercomm login pages.
        for marker in ("var myNonce", "var loginNonce", "loginToken"):
            idx = text.find(marker)
            if idx != -1:
                snippet = text[idx: idx + 120]
                _LOGGER.debug("Found potential nonce marker %r near: %s", marker, snippet)

        return ""

    async def login(self) -> bool:
        """Authenticate against the router. Returns True on success."""
        nonce = await self._get_login_nonce()
        encrypted = self._encrypt_password(nonce)

        url = f"{self._base_url}{LOGIN_ENDPOINT}?_n={_cache_buster()}"
        payload = {
            "AuthData": "loginPassword",
            "EncryptData": encrypted,
            "Name": self._username,
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self._base_url}{LOGIN_PAGE}",
        }

        try:
            async with self._session.post(
                url, data=payload, headers=headers, timeout=DEFAULT_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    raise VodafoneStationConnectionError(
                        f"Unexpected status {resp.status} posting to {url}"
                    )
                body = await resp.text()
        except aiohttp.ClientError as err:
            raise VodafoneStationConnectionError(
                f"Connection error communicating with Vodafone Station at {url}: {err}"
            ) from err

        _LOGGER.debug("Login response: %s", body)

        # Sercomm firmwares typically respond with a JSON blob containing
        # something like {"status": "success"} or an error code/message on
        # failure. Adjust this check once you've seen a real success payload.
        if '"status"' in body and "success" in body.lower():
            self._logged_in = True
            return True

        if "error" in body.lower() or "fail" in body.lower():
            _LOGGER.warning(
                "Failed to authenticate with Vodafone Station. "
                "Invalid credentials, or the encryption scheme in "
                "_encrypt_password doesn't match this firmware yet."
            )
            return False

        # Unknown response shape — log it so it can be inspected and the
        # success/failure check above refined.
        _LOGGER.warning(
            "Unrecognized login response from Vodafone Station; "
            "treating as failure. Body was: %s",
            body[:500],
        )
        return False

    async def _ensure_logged_in(self) -> None:
        if not self._logged_in and not await self.login():
            raise VodafoneStationAuthError("Not authenticated with Vodafone Station")

    async def _get_json(self, endpoint: str) -> Any:
        await self._ensure_logged_in()
        url = f"{self._base_url}{endpoint}?_n={_cache_buster()}"
        try:
            async with self._session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status == 401 or resp.status == 403:
                    # Session expired — retry once after a fresh login.
                    self._logged_in = False
                    await self._ensure_logged_in()
                    async with self._session.get(url, timeout=DEFAULT_TIMEOUT) as retry_resp:
                        retry_resp.raise_for_status()
                        return await retry_resp.json(content_type=None)
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise VodafoneStationConnectionError(
                f"Connection error fetching {url}: {err}"
            ) from err

    async def async_get_data(self) -> dict[str, Any]:
        """Poll the router and normalize data for the coordinator.

        NOTE: the endpoint names/JSON shapes here are placeholders matching
        what other Sercomm Vodafone Station models expose. Once login is
        confirmed working, inspect the Network tab for the actual endpoints
        this router's dashboard calls (system info, DOCSIS, Wi-Fi, connected
        devices) and adjust the paths and parsing below to match.
        """
        sys_info_raw = await self._get_json(SYSINFO_ENDPOINT)
        devices_raw = await self._get_json(DEVICES_ENDPOINT)

        return {
            "sys_info": {
                "firmware": sys_info_raw.get("firmware", "Unknown"),
                "wan_status": sys_info_raw.get("wan_status", "Unknown"),
                "wan_ip": sys_info_raw.get("wan_ip", "Unknown"),
            },
            "docsis": {
                "downstream_snr": sys_info_raw.get("downstream_snr"),
                "upstream_power": sys_info_raw.get("upstream_power"),
            },
            "wifi": {
                "2g_enabled": sys_info_raw.get("wifi_2g_enabled", False),
                "5g_enabled": sys_info_raw.get("wifi_5g_enabled", False),
                "guest_enabled": sys_info_raw.get("wifi_guest_enabled", False),
            },
            "devices": {
                mac: {"name": info.get("name", mac), "connected": info.get("connected", False)}
                for mac, info in devices_raw.items()
            } if isinstance(devices_raw, dict) else {},
        }

    async def async_reboot(self) -> bool:
        """Trigger a router reboot."""
        await self._ensure_logged_in()
        url = f"{self._base_url}{REBOOT_ENDPOINT}?_n={_cache_buster()}"
        try:
            async with self._session.post(
                url, data={"restart": "1"}, timeout=DEFAULT_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                return True
        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to reboot Vodafone Station: %s", err)
            return False

    async def async_set_wifi_state(self, band: str, enabled: bool) -> bool:
        """Enable or disable a Wi-Fi radio band ('2g', '5g', or 'guest')."""
        await self._ensure_logged_in()
        url = f"{self._base_url}{WIFI_ENDPOINT}?_n={_cache_buster()}"
        payload = {"band": band, "enabled": "1" if enabled else "0"}
        try:
            async with self._session.post(
                url, data=payload, timeout=DEFAULT_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                return True
        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to set Wi-Fi state (%s -> %s): %s", band, enabled, err)
            return False
