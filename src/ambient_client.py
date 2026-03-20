"""
ambient_client.py - Ambient Weather REST API Client
====================================================

This module handles all communication with the Ambient Weather REST API.

TWO ENDPOINTS:
--------------
1. GET /v1/devices
   → Returns all your weather stations + their most recent reading

2. GET /v1/devices/:macAddress
   → Returns historical readings for one station (5-min intervals)

AUTHENTICATION:
--------------
Both endpoints require two query parameters:
  ?apiKey=YOUR_API_KEY&applicationKey=YOUR_APP_KEY

No headers, no tokens — just query params. Simple.

RATE LIMITS:
-----------
- 1 request/second per apiKey
- 3 requests/second per applicationKey
- Exceeding = HTTP 429 response

To stay within limits, we cache responses for 60 seconds.
Weather stations only report every 5 minutes anyway, so
caching for 60 seconds loses nothing.

API DOCS: https://ambientweather.docs.apiary.io/
"""

import time
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)

# The REST API base URL.
# "rt" = REST API. There's also "rt2" for the WebSocket API, but we don't use that.
BASE_URL = "https://rt.ambientweather.net/v1"


# -------------------------------------------------------------------------
# Custom exception
# -------------------------------------------------------------------------

class AmbientWeatherError(Exception):
    """Raised when the Ambient Weather API returns an error.

    We use a custom exception so the MCP tool handlers can distinguish
    between "the API returned an error" vs "our code has a bug".
    """
    pass


# -------------------------------------------------------------------------
# Simple cache
# -------------------------------------------------------------------------

class CacheEntry:
    """One cached API response with a timestamp.

    When we fetch data from the API, we store it here along with
    the current time. Before making a new API call, we check if
    we already have a recent-enough cached response.
    """

    def __init__(self, data: Any):
        self.data = data
        self.created_at = time.time()

    def is_expired(self, ttl_seconds: int) -> bool:
        """Has this entry been sitting here longer than ttl_seconds?"""
        age = time.time() - self.created_at
        return age > ttl_seconds


# -------------------------------------------------------------------------
# The API client
# -------------------------------------------------------------------------

class AmbientWeatherClient:
    """Client for the Ambient Weather REST API.

    Usage:
        client = AmbientWeatherClient(
            api_key=d6ab3f0d0f0046afbf9dbcc2c2c7fc025e351862d4804bcea3192c3a9e734f7c,
            app_key=5ca27fa20eb84af6b38360c0db84f8b4e700b61436984b4a885c5e78e1c436c0,
        )

        # List all stations
        devices = await client.get_devices()

        # Get history for one station
        history = await client.get_device_data("AA:BB:CC:DD:EE:FF", limit=12)

        # Clean up when done
        await client.close()
    """

    def __init__(self, api_key: str, app_key: str, cache_ttl_seconds: int = 60):
        """
        Args:
            api_key: Your Ambient Weather API key (identifies the user).
            app_key: Your Ambient Weather Application key (identifies the app).
            cache_ttl_seconds: How long to cache responses (default 60s).
                Set to 0 to disable caching (not recommended).
        """
        # --- Validate inputs ---
        if not api_key or not api_key.strip():
            raise ValueError(
                "AMBIENT_API_KEY is required. "
                "Get yours at https://dashboard.ambientweather.net/account"
            )
        if not app_key or not app_key.strip():
            raise ValueError(
                "AMBIENT_APP_KEY is required. "
                "Get yours at https://dashboard.ambientweather.net/account"
            )

        self._api_key = api_key.strip()
        self._app_key = app_key.strip()
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, CacheEntry] = {}

        # We create the HTTP client here (not lazily) for simplicity.
        # httpx.AsyncClient reuses connections across requests (connection pooling).
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(30.0),
            headers={
                "Accept": "application/json",
                "User-Agent": "ambient-weather-mcp/0.1.0",
            },
        )

    # -----------------------------------------------------------------
    # Cache helpers
    # -----------------------------------------------------------------

    def _get_cached(self, key: str) -> Any | None:
        """Return cached data if it exists and hasn't expired."""
        if self._cache_ttl <= 0:
            return None  # Caching disabled

        entry = self._cache.get(key)
        if entry is None:
            return None

        if entry.is_expired(self._cache_ttl):
            del self._cache[key]
            return None

        logger.debug("Cache hit: %s", key)
        return entry.data

    def _set_cached(self, key: str, data: Any) -> None:
        """Store data in cache."""
        if self._cache_ttl > 0:
            self._cache[key] = CacheEntry(data)

    # -----------------------------------------------------------------
    # Core HTTP method
    # -----------------------------------------------------------------

    async def _request(self, endpoint: str, extra_params: dict | None = None) -> Any:
        """Make an authenticated GET request to the Ambient Weather API.

        This is the single method that all public methods go through.

        Args:
            endpoint: API path, e.g. "/devices" or "/devices/AA:BB:CC"
            extra_params: Additional query params beyond the auth keys.

        Returns:
            Parsed JSON response (usually a list of dicts).

        Raises:
            AmbientWeatherError: On any API error (auth, rate limit, server error).
        """
        # --- Check cache first ---
        cache_key = f"{endpoint}|{extra_params}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # --- Build request params ---
        # Auth is done via query parameters, not headers
        params = {
            "apiKey": self._api_key,
            "applicationKey": self._app_key,
        }
        if extra_params:
            params.update(extra_params)

        # --- Make the request ---
        try:
            logger.info("GET %s", endpoint)
            response = await self._http.get(endpoint, params=params)

        except httpx.TimeoutException:
            raise AmbientWeatherError(
                "Request timed out after 30 seconds. "
                "The Ambient Weather API may be slow or unreachable."
            )
        except httpx.ConnectError:
            raise AmbientWeatherError(
                "Could not connect to rt.ambientweather.net. "
                "Check your internet connection."
            )
        except httpx.HTTPError as exc:
            raise AmbientWeatherError(f"HTTP error: {exc}")

        # --- Handle response status codes ---
        if response.status_code == 200:
            data = response.json()
            self._set_cached(cache_key, data)
            return data

        elif response.status_code == 401:
            raise AmbientWeatherError(
                "Authentication failed (401). Your API keys are invalid. "
                "Check AMBIENT_API_KEY and AMBIENT_APP_KEY. "
                "Generate new keys at https://dashboard.ambientweather.net/account"
            )

        elif response.status_code == 429:
            raise AmbientWeatherError(
                "Rate limit exceeded (429). The API allows 1 request/second. "
                "Wait a moment and retry."
            )

        elif response.status_code == 404:
            raise AmbientWeatherError(
                f"Not found (404) for {endpoint}. "
                "Check that the MAC address is correct."
            )

        elif response.status_code >= 500:
            raise AmbientWeatherError(
                f"Ambient Weather server error ({response.status_code}). "
                "Try again later."
            )

        else:
            raise AmbientWeatherError(
                f"Unexpected response: {response.status_code} - "
                f"{response.text[:200]}"
            )

    # -----------------------------------------------------------------
    # Public methods (these are what the MCP tools will call)
    # -----------------------------------------------------------------

    async def get_devices(self) -> list[dict]:
        """Fetch all weather stations and their latest readings.

        Returns:
            List of device dicts. Each contains:
            - "macAddress": the station's unique ID
            - "lastData": dict of the most recent weather reading
            - "info": dict with station name, location, etc.
        """
        result = await self._request("/devices")

        if not result:
            logger.warning("No devices found for this API key")

        return result

    async def get_device_data(
        self,
        mac_address: str,
        limit: int = 288,
        end_date: str | None = None,
    ) -> list[dict]:
        """Fetch historical readings for one station.

        Args:
            mac_address: The station's MAC address (from get_devices).
            limit: Max readings to return, 1-288. (288 = 24 hours at 5-min intervals)
            end_date: Optional. Start fetching from this time backwards.
                ISO 8601 format or milliseconds since epoch.
                If omitted, starts from the most recent reading.

        Returns:
            List of reading dicts, newest first.
        """
        # --- Validate inputs ---
        if not mac_address or not mac_address.strip():
            raise ValueError("mac_address is required")

        if limit < 1 or limit > 288:
            raise ValueError("limit must be between 1 and 288")

        # --- Build params ---
        params: dict[str, Any] = {"limit": limit}
        if end_date:
            params["endDate"] = end_date

        return await self._request(
            f"/devices/{mac_address.strip()}",
            extra_params=params,
        )

    async def close(self) -> None:
        """Close the HTTP client. Call this when shutting down."""
        await self._http.aclose()
        logger.info("HTTP client closed")
