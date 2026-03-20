"""
server.py - Ambient Weather MCP Server
========================================

HOW MCP WORKS:
--------------
1. An MCP "server" exposes "tools" — functions that an AI can call.
2. An MCP "client" (Claude Desktop, VS Code, Kiro) discovers these tools.
3. When the AI decides to use a tool, the client sends a JSON-RPC message
   to this server via stdin.
4. This server runs the tool function and writes the result to stdout.
5. The client reads the result and the AI presents it in natural language.

WHAT THIS FILE DOES (Phase 4):
-------------------------------
- Creates a FastMCP server
- Creates an AmbientWeatherClient to talk to the weather API
- Defines three tools:
    ping              → health check (from Phase 2)
    get_devices       → list all your weather stations
    get_current_weather → get latest readings from a specific station
- Handles errors gracefully (missing keys, API failures, bad MAC addresses)

HOW TO RUN:
-----------
  python -m src
"""

import os
import sys
import logging

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.ambient_client import AmbientWeatherClient, AmbientWeatherError


# -------------------------------------------------------------------------
# Step 1: Load configuration
# -------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("ambient-weather-mcp")


# -------------------------------------------------------------------------
# Step 2: Read API keys and create the API client
# -------------------------------------------------------------------------

AMBIENT_API_KEY = os.getenv("AMBIENT_API_KEY", "")
AMBIENT_APP_KEY = os.getenv("AMBIENT_APP_KEY", "")

# The API client is None if keys are missing.
# Each tool checks for this and returns a helpful error message.
api_client: AmbientWeatherClient | None = None

if AMBIENT_API_KEY and AMBIENT_APP_KEY:
    try:
        api_client = AmbientWeatherClient(
            api_key=AMBIENT_API_KEY,
            app_key=AMBIENT_APP_KEY,
        )
        logger.info("API client initialized successfully")
    except ValueError as e:
        logger.error("Failed to create API client: %s", e)
else:
    if not AMBIENT_API_KEY:
        logger.warning("AMBIENT_API_KEY is not set.")
    if not AMBIENT_APP_KEY:
        logger.warning("AMBIENT_APP_KEY is not set.")
    logger.warning(
        "Weather tools will return errors until both keys are configured. "
        "Get your keys at https://dashboard.ambientweather.net/account"
    )


# -------------------------------------------------------------------------
# Step 3: Create the MCP server
# -------------------------------------------------------------------------

mcp = FastMCP(
    name="ambient-weather",
    instructions=(
        "Access real-time and historical data from Ambient Weather "
        "personal weather stations. Use get_devices first to find "
        "station MAC addresses, then use get_current_weather with "
        "a MAC address to get readings."
    ),
)


# -------------------------------------------------------------------------
# Helper: check API client is ready
# -------------------------------------------------------------------------

def _check_client() -> str | None:
    """Check if the API client is initialized.

    Returns:
        None if client is ready.
        An error message string if client is not ready.
    """
    if api_client is None:
        return (
            "Error: API client is not initialized.\n"
            "Make sure AMBIENT_API_KEY and AMBIENT_APP_KEY are set.\n"
            "Get your keys at https://dashboard.ambientweather.net/account"
        )
    return None


# -------------------------------------------------------------------------
# Step 4: Define tools
# -------------------------------------------------------------------------

@mcp.tool()
async def ping() -> str:
    """Check if the Ambient Weather MCP server is running and responsive.

    Returns server status and whether API keys are configured.
    """
    logger.info("ping called")

    api_key_status = "configured" if AMBIENT_API_KEY else "MISSING"
    app_key_status = "configured" if AMBIENT_APP_KEY else "MISSING"
    client_status = "ready" if api_client is not None else "NOT INITIALIZED"

    return (
        f"Ambient Weather MCP server is running.\n"
        f"API Key: {api_key_status}\n"
        f"Application Key: {app_key_status}\n"
        f"API Client: {client_status}"
    )


@mcp.tool()
async def get_devices() -> str:
    """List all Ambient Weather stations on your account.

    Returns the name, location, MAC address, and latest conditions
    for each station. Use the MAC address from this output when
    calling get_current_weather.

    No parameters needed.
    """
    logger.info("get_devices called")

    # Check if client is ready
    error = _check_client()
    if error:
        return error

    try:
        devices = await api_client.get_devices()

        if not devices:
            return (
                "No weather stations found for this account.\n"
                "Make sure your station is online and registered at "
                "https://ambientweather.net"
            )

        # Format each device into a readable summary
        results = []
        for i, device in enumerate(devices, 1):
            mac = device.get("macAddress", "Unknown")
            info = device.get("info", {})
            name = info.get("name", "Unnamed Station")
            location = info.get("location", "Unknown location")
            last_data = device.get("lastData", {})

            # Pull a few key readings from lastData
            temp = last_data.get("tempf")
            humidity = last_data.get("humidity")
            date = last_data.get("date", "No recent data")

            lines = [
                f"--- Station {i} ---",
                f"Name: {name}",
                f"Location: {location}",
                f"MAC Address: {mac}",
                f"Last Report: {date}",
            ]

            if temp is not None:
                lines.append(f"Temperature: {temp}°F")
            if humidity is not None:
                lines.append(f"Humidity: {humidity}%")

            results.append("\n".join(lines))

        return "\n\n".join(results)

    except AmbientWeatherError as e:
        return f"Error: {e}"


@mcp.tool()
async def get_current_weather(mac_address: str) -> str:
    """Get the current weather conditions from a specific station.

    Returns temperature, humidity, wind, pressure, rain, and more.

    Args:
        mac_address: The MAC address of the weather station.
            Get this from the get_devices tool.
            Example: "AA:BB:CC:DD:EE:FF"
    """
    logger.info("get_current_weather called for %s", mac_address)

    # Check if client is ready
    error = _check_client()
    if error:
        return error

    try:
        # Fetch just the 1 most recent reading
        readings = await api_client.get_device_data(mac_address, limit=1)

        if not readings:
            return (
                f"No data available for station {mac_address}.\n"
                "The station may be offline or not reporting."
            )

        # readings is a list; take the first (most recent) one
        data = readings[0]
        date = data.get("date", "Unknown time")

        # Build a readable weather report from the raw fields
        lines = [f"Current Weather (as of {date}):"]

        # Temperature
        temp = data.get("tempf")
        if temp is not None:
            feels = data.get("feelsLike")
            line = f"  Temperature: {temp}°F"
            if feels is not None and feels != temp:
                line += f" (feels like {feels}°F)"
            lines.append(line)

        # Humidity + Dew Point
        humidity = data.get("humidity")
        if humidity is not None:
            lines.append(f"  Humidity: {humidity}%")

        dew = data.get("dewPoint")
        if dew is not None:
            lines.append(f"  Dew Point: {round(dew, 1)}°F")

        # Wind
        wind_speed = data.get("windspeedmph")
        if wind_speed is not None:
            wind_dir = data.get("winddir")
            line = f"  Wind: {wind_speed} mph"
            if wind_dir is not None:
                line += f" from {_degrees_to_compass(wind_dir)}"
            lines.append(line)

        gust = data.get("windgustmph")
        if gust is not None and gust > 0:
            lines.append(f"  Wind Gust: {gust} mph")

        # Pressure
        pressure = data.get("baromrelin")
        if pressure is not None:
            lines.append(f"  Pressure: {pressure} inHg (relative)")

        # Rain
        hourly_rain = data.get("hourlyrainin")
        if hourly_rain is not None:
            lines.append(f"  Rain (hourly): {hourly_rain} in")

        daily_rain = data.get("dailyrainin")
        if daily_rain is not None:
            lines.append(f"  Rain (daily): {daily_rain} in")

        # UV
        uv = data.get("uv")
        if uv is not None:
            lines.append(f"  UV Index: {uv}")

        # Solar
        solar = data.get("solarradiation")
        if solar is not None:
            lines.append(f"  Solar Radiation: {solar} W/m²")

        # Indoor
        temp_in = data.get("tempinf")
        humid_in = data.get("humidityin")
        if temp_in is not None or humid_in is not None:
            lines.append("  Indoor:")
            if temp_in is not None:
                lines.append(f"    Temperature: {temp_in}°F")
            if humid_in is not None:
                lines.append(f"    Humidity: {humid_in}%")

        return "\n".join(lines)

    except ValueError as e:
        return f"Invalid input: {e}"
    except AmbientWeatherError as e:
        return f"Error: {e}"


# -------------------------------------------------------------------------
# Helper: wind direction degrees to compass direction
# -------------------------------------------------------------------------

def _degrees_to_compass(degrees: float) -> str:
    """Convert 0-360 degrees to compass direction (N, NE, E, etc.)."""
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    ]
    index = round(degrees % 360 / 22.5) % 16
    return directions[index]


# -------------------------------------------------------------------------
# Step 5: Entry point
# -------------------------------------------------------------------------

def main():
    """Start the MCP server in stdio mode."""
    logger.info("Starting Ambient Weather MCP server (stdio mode)...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
