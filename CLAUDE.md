# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Clove is a Claude.ai reverse proxy that allows access to Claude through standard API endpoints. It supports two modes:
- **OAuth mode**: Primary mode using Claude's official API with full functionality
- **Web reverse proxy mode**: Fallback mode simulating Claude.ai web interface

**IMPORTANT**: This project currently **ONLY uses the Web reverse proxy mode** (claude-web-api processing flow). The OAuth API mode is not enabled or configured in this deployment.

## Development Commands

### Backend (Python/FastAPI)

```bash
# Install dependencies (with rnet support)
pip install "clove-proxy[rnet]"

# Install from source with dev dependencies
pip install -e ".[rnet,dev]"

# Run the application
clove
# or
python -m app.main

# Build wheel
python scripts/build_wheel.py
```

### Frontend (React/Vite)

```bash
cd front

# Install dependencies (using pnpm)
pnpm install

# Development server
pnpm dev

# Build for production
pnpm build

# Lint
pnpm lint
```

### Docker

```bash
# Build and run with Docker Compose
docker-compose up --build

# Run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f
```

## Architecture

### Backend Structure

The backend follows a processor pipeline architecture:

1. **Request Flow**: `app/api/routes/claude.py` receives API requests
2. **Processing Pipeline**: `app/processors/claude_ai/pipeline.py` orchestrates request processing through multiple processors
3. **Processors** (in `app/processors/claude_ai/`):
   - `claude_api_processor.py`: Handles OAuth API requests
   - `claude_web_processor.py`: Handles web reverse proxy requests
   - `event_parser_processor.py`: Parses server-sent events
   - `tool_call_event_processor.py`: Processes tool call events
   - `streaming_response_processor.py`: Handles streaming responses
   - `non_streaming_response_processor.py`: Handles non-streaming responses
   - Other processors handle token counting, stop sequences, etc.

### Key Components

- **Session Management** (`app/services/session.py`): Manages Claude.ai session lifecycle
- **Account Management** (`app/services/account.py`): Handles multiple Claude accounts, quotas, and OAuth authentication
- **OAuth Service** (`app/services/oauth.py`): Manages OAuth authentication flow for Claude API access
- **HTTP Client** (`app/core/http_client.py`): Centralized HTTP client with retry logic

### Frontend Structure

- React + TypeScript + Vite
- Tailwind CSS + Shadcn UI components
- React Router for routing
- Admin interface at `http://localhost:5201`

### Configuration

Settings are managed through:
1. `app/core/config.py`: Central configuration using Pydantic settings
2. Environment variables (`.env` file)
3. JSON config file (stored in `DATA_FOLDER/config.json`)

Priority: JSON config > Environment variables > Default values

## Important Notes

### Python Output Encoding on Windows

When running Python scripts that output Chinese characters on Windows:
- Add `sys.stdout.reconfigure(encoding='utf-8')` at the script beginning
- Or set environment variable: `set PYTHONIOENCODING=utf-8`
- Windows CMD/PowerShell uses GBK by default, Python 3 uses UTF-8

### Running Django-style Scripts

While this is a FastAPI project, if you need to run standalone scripts that import from `app`:
- Create a temporary launcher script that sets `sys.path` at the beginning
- Avoid using `python -c` with Chinese characters in file paths
- Use consistent path separators (prefer forward slashes)

### Dependencies

- **rnet**: Required for OAuth functionality and web scraping
- **curl-cffi**: Required for web reverse proxy (not available on Android Termux)
- Use `pip install clove-proxy` for minimal installation without curl-cffi
- Use `pip install "clove-proxy[rnet]"` for full functionality

## Testing

The project includes test message processing in `app/processors/claude_ai/tavern_test_message_processor.py` for SillyTavern compatibility testing.

## Data Storage

- **Production**: Data stored in `DATA_FOLDER` (default: `~/.clove/data`)
- **Docker**: Data persists in `/data` volume
- **NO_FILESYSTEM_MODE**: When enabled, stores everything in memory (no persistence)

Account data and settings are automatically saved to `DATA_FOLDER/accounts.json` and `DATA_FOLDER/config.json`.
