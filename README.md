# Ambient Weather MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that connects AI assistants to [Ambient Weather](https://ambientweather.com/) personal weather station data. Ask natural language questions about your weather station instead of parsing raw JSON from the API.

## What It Does

This server exposes your Ambient Weather station data as MCP tools. Connect it to Claude Desktop, VS Code, or Kiro, and you can ask things like:

- "List my weather stations"
- "What's the current temperature at my station?"
- "What are the conditions at CC:7B:5C:51:EC:52?"

The AI calls the tool, the server fetches live data from the Ambient Weather REST API, and the AI presents the result in natural language.

## Architecture

```
┌──────────────────┐    stdio (JSON-RPC)    ┌────────────────────┐
│   MCP Client     │◄─────────────────────►│   MCP Server       │
│  Claude Desktop  │                        │   (this project)   │
│  VS Code / Kiro  │                        │                    │
└──────────────────┘                        │  src/server.py     │
                                            │    ↓ calls          │
                                            │  src/ambient_client │
                                            │    ↓ HTTPS          │
                                            └────────┬───────────┘
                                                     │
                                            ┌────────▼───────────┐
                                            │  Ambient Weather   │
                                            │  REST API          │
                                            │  rt.ambientweather │
                                            │  .net/v1           │
                                            └────────────────────┘
```

## Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `ping` | Health check — confirms server is running and keys are configured | None |
| `get_devices` | Lists all weather stations on the account with latest readings | None |
| `get_current_weather` | Full weather report from a specific station | `mac_address` |

## Prerequisites

1. **Ambient Weather API keys** — generate both at https://dashboard.ambientweather.net/account
   - **Application Key**: identifies the MCP server app
   - **API Key**: grants read access to device data
2. **Python 3.11+** installed
3. **An Ambient Weather station** reporting to ambientweather.net (or access to someone's API key who has one)

## Setup (Local Development)

```bash
# Clone the repo
git clone https://github.com/NanaGyamfiPrempeh30/ambient-weather-mcp.git
cd ambient-weather-mcp

# Create virtual environment
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
source venv/Scripts/activate    # Windows Git Bash

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your actual keys

# Test the server
python3 -c "from src.server import ping; import asyncio; print(asyncio.run(ping()))"
```

You should see:
```
Ambient Weather MCP server is running.
API Key: configured
Application Key: configured
API Client: ready
```

## Connecting to Claude Desktop

### Windows (with batch file)

1. Create `run_mcp.bat` in the project root:
```bat
@echo off
cd /d C:\Users\YourUsername\ambient-weather-mcp
C:\Python313\python.exe -m src
```

2. Add to `claude_desktop_config.json` (found at `%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "ambient-weather": {
      "command": "cmd.exe",
      "args": ["/c", "C:\\Users\\YourUsername\\ambient-weather-mcp\\run_mcp.bat"],
      "env": {
        "AMBIENT_API_KEY": "your-api-key",
        "AMBIENT_APP_KEY": "your-application-key"
      }
    }
  }
}
```

### macOS / Linux (direct)

Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "ambient-weather": {
      "command": "python3",
      "args": ["-m", "src"],
      "cwd": "/path/to/ambient-weather-mcp",
      "env": {
        "AMBIENT_API_KEY": "your-api-key",
        "AMBIENT_APP_KEY": "your-application-key"
      }
    }
  }
}
```

3. Restart Claude Desktop fully (quit from system tray, reopen).
4. Check Settings → Developer → ambient-weather shows **running**.
5. In a new chat, ask: "Use the get_devices tool to list my weather stations"

## Running with Docker

```bash
# Build
docker build -t ambient-weather-mcp .

# Run
docker run -i --rm \
  -e AMBIENT_API_KEY="your-api-key" \
  -e AMBIENT_APP_KEY="your-app-key" \
  ambient-weather-mcp
```

## Project Structure

```
ambient-weather-mcp/
├── src/
│   ├── __init__.py          # Package marker
│   ├── __main__.py          # Entry point for python -m src
│   ├── server.py            # MCP server + tool definitions
│   └── ambient_client.py    # Ambient Weather REST API client
├── .env.example             # API key template (safe to commit)
├── .gitignore               # Excludes .env, venv, __pycache__
├── .dockerignore             # Excludes secrets from Docker image
├── Dockerfile               # Container build recipe
├── run_mcp.bat              # Windows launcher for Claude Desktop
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## API Rate Limits

The Ambient Weather API enforces:
- 1 request/second per API key
- 3 requests/second per Application key

The server includes a 60-second TTL cache to stay within these limits automatically. Weather stations only report every 5 minutes, so caching loses nothing.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AMBIENT_API_KEY` | Yes | Ambient Weather API key |
| `AMBIENT_APP_KEY` | Yes | Ambient Weather Application key |
| `CACHE_TTL_SECONDS` | No | Cache duration in seconds (default: 60) |
| `LOG_LEVEL` | No | DEBUG, INFO, WARNING, ERROR (default: INFO) |

## Troubleshooting

**"No module named src"** — Python can't find the project. Make sure you're running from the project root directory, or use the batch file approach on Windows.

**"Server disconnected" in Claude Desktop** — On Windows, use the `cmd.exe` + batch file method shown above. Direct Python execution has working directory issues with Claude Desktop.

**"401 Unauthorized"** — API keys are invalid. Regenerate at https://dashboard.ambientweather.net/account

**"No weather stations found"** — The API key doesn't have any stations attached. You need a physical Ambient Weather station registered to the account.

**"429 Too Many Requests"** — Rate limit hit. Wait a few seconds. Increase `CACHE_TTL_SECONDS` if it keeps happening.

## What's Next

- [ ] `get_weather_history` tool for historical data queries
- [ ] Publish Docker image to Docker Hub
- [ ] Comprehensive README with Wilson's station as a live demo
- [ ] Extend with Kiro spec-driven workflow for additional features
- [ ] MCP OAuth authorization for secure multi-user access
- [ ] Consider secrets manager integration (macOS Keychain, etc.)

## Credits

- [Ambient Weather API](https://ambientweather.docs.apiary.io/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP](https://github.com/jlowin/fastmcp)
- Built by [Yaw (NGP-Dev)](https://github.com/NanaGyamfiPrempeh30)
- Wilson Mar — mentorship, weather station access, [MCP reference](https://wilsonmar.github.io/mcp/), [weather-info](https://wilsonmar.github.io/weather-info/)

## License

MIT
