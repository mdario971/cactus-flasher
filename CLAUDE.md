# CLAUDE.md - Cactus Flasher Project Memory

## Project Overview
**Cactus Flasher** is an ESP32 Web Flasher application for OTA firmware updates.
- **Location**: Configurable — installed via `install.sh` in any directory
- **Framework**: FastAPI (Python 3.13) + Vanilla JS frontend
- **VPS**: Debian 12, user configurable (set during install), protected by Cactus Sentinel (fail2ban)
- **Installer**: `install.sh` — interactive, asks for user, auto-configures everything
- **Deploy**: `deploy.sh` — auto-detects paths, no hardcoded values
- **Status**: Auth flow WORKING and TESTED as of 2026-02-11

## CRITICAL - Do NOT Change These (Working Code)

### Authentication Flow (VERIFIED WORKING)
- **Library**: `python-jose[cryptography]` for JWT, `bcrypt` for password hashing
- **Security scheme**: `HTTPBearer` (NOT OAuth2PasswordBearer)
- **Token format**: `Authorization: Bearer <jwt_token>`
- **Login endpoint**: `POST /api/auth/login` - accepts JSON `{username, password}`, returns `{access_token, token_type, username}`
- **Token validation**: `GET /api/auth/me` - returns `{username}`
- **Default admin**: username `admin`, password `cactus123` (auto-created on first startup, skip_validation=True)
- **Password policy**: min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char — enforced by `validate_password()`
- **JWT config**: HS256 algorithm, 60 min expiry, secret key in `settings.SECRET_KEY`
- **Password storage**: bcrypt with 12 rounds, stored in `config/credentials.yaml`
- **User management**: list users, change password, delete user (cannot delete self or last user)
- **Auth dependency**: `get_current_user()` returns username string, uses `Depends(security)` where `security = HTTPBearer()`

### Frontend Auth (VERIFIED WORKING)
- Token stored in `localStorage` as `token` and `username`
- On load: checks stored token via `/api/auth/me`, shows login modal if invalid
- Login form POSTs to `/api/auth/login`, stores token on success
- All API calls include `Authorization: Bearer ${this.token}` header
- 401 responses trigger automatic logout

## File Structure
```
cactus-flasher/
  app/
    __init__.py          # Package marker
    main.py              # FastAPI app, CORS, WebSocket, auth endpoints
    auth.py              # JWT + bcrypt auth (HTTPBearer scheme)
    config.py            # Settings, YAML config loader, board port calculator
    models/
      __init__.py
      schemas.py         # Pydantic models (Login, Board, Build, Flash, WS, Sensor)
    routers/
      __init__.py
      boards.py          # CRUD + scan + ping + status-log for boards
      build.py           # ESPHome/Arduino/PlatformIO compilation
      flash.py           # OTA firmware upload + flash
    services/
      __init__.py
      arduino.py         # arduino-cli compilation
      esphome.py         # ESPHome compilation
      platformio.py      # PlatformIO compilation
      ota.py             # HTTP OTA flash (multipart + chunked)
      scanner.py         # TCP/HTTP board scanning + discovery + MAC/sensor auto-discovery
      status_logger.py   # Persistent board online/offline status logging
      sensors.py         # ESPHome web_server sensor scraping/discovery
  config/
    boards.yaml          # Board registry (name -> id, type, host, mac_address, last_seen, sensors)
    credentials.yaml     # User credentials (bcrypt hashes)
    board_status_log.yaml # Persistent board status transition log (auto-created)
  static/
    index.html           # SPA with Tailwind CSS dark theme (5 tabs: Boards, Upload, Builds, Settings, Guide)
    css/style.css        # Custom styles (cards, badges, animations, tooltips)
    js/app.js            # CactusFlasher class (auth, boards, build, flash, status log, sensors)
  venv/                  # Python virtual environment (Python 3.13)
  install.sh             # Interactive installer (creates user, venv, service, nginx)
  deploy.sh              # Deploy/rollback script (auto-detects paths)
  cactus-flasher.service # Systemd unit template (install.sh generates the real one)
  Dockerfile             # Python 3.13-slim for Docker
  docker-compose.yml     # Local dev (hot reload)
  docker-compose.prod.yml # Production Docker (optional)
  .env.example           # Environment variable template
  requirements.txt       # Dependencies
  README.md              # Full documentation + installation guide
  CLAUDE.md              # THIS FILE
```

## API Routes Map
| Method | Path | Auth | Handler |
|--------|------|------|---------|
| POST | /api/auth/login | No | main.py:login |
| POST | /api/auth/register | Yes | main.py:register |
| GET | /api/auth/me | Yes | main.py:get_me |
| GET | /api/auth/users | Yes | main.py:get_users |
| PUT | /api/auth/change-password | Yes | main.py:api_change_password |
| DELETE | /api/auth/users/{username} | Yes | main.py:api_delete_user |
| GET | /api/boards | No | boards.py:list_boards |
| POST | /api/boards | No | boards.py:create_board |
| GET | /api/boards/scan | No | boards.py:scan_boards |
| GET | /api/boards/status-log | No | boards.py:get_board_status_log |
| GET | /api/boards/discover | No | boards.py:discover_boards |
| GET | /api/boards/{name}/logs | No | boards.py:stream_board_logs |
| GET | /api/boards/{name} | No | boards.py:get_board |
| PUT | /api/boards/{name} | No | boards.py:update_board |
| DELETE | /api/boards/{name} | No | boards.py:delete_board |
| POST | /api/boards/{name}/ping | No | boards.py:ping_board |
| POST | /api/build/esphome | No | build.py:build_esphome |
| POST | /api/build/arduino | No | build.py:build_arduino |
| POST | /api/build/platformio | No | build.py:build_platformio |
| GET | /api/build/status/{id} | No | build.py:get_build_status |
| GET | /api/build/logs/{id} | No | build.py:get_build_logs |
| GET | /api/build/list | No | build.py:list_builds |
| POST | /api/flash/upload | No | flash.py:upload_firmware |
| POST | /api/flash/from-build | No | flash.py:flash_from_build |
| GET | /api/flash/status/{id} | No | flash.py:get_flash_status |
| GET | /api/flash/history | No | flash.py:get_flash_history |
| WS | /ws | No | main.py:websocket_endpoint |

## Board Port Convention
Board ID `XX` (01-99) maps to:
- **Webserver**: `80XX` (e.g., ID 88 -> port 8088)
- **OTA**: `82XX` (e.g., ID 88 -> port 8288)
- **Native API**: `60XX` (e.g., ID 88 -> port 6088)
- Calculated in `config.py:get_board_ports(board_id)`

## Board Hostname Convention
- Auto-generated: strip `cactus-`/`esp32-`/`esp-` prefix, format `{shortname}-{ID:02d}.{DDNS_HOST}`
- Example: `cactus-sentinel` ID 88 -> `sentinel-88.esp32gb.ddns.net`
- Custom hostname overrides auto-generation (stored in boards.yaml)
- Calculated in `config.py:get_board_hostname(board_name, board_id, custom_hostname)`

## Network Topology
```
VPS (cactus-flasher on port 8000)
  -> DDNS: esp32gb.ddns.net
  -> Home Router (port forwarding per board)
  -> ESP32 boards on local network
```

## Key Dependencies (requirements.txt)
- fastapi>=0.104.0, uvicorn[standard]>=0.24.0
- python-jose[cryptography]>=3.3.0, bcrypt>=4.1.0
- python-multipart>=0.0.6, pyyaml>=6.0.1
- aiohttp>=3.9.0, websockets>=12.0

## Common Pitfalls to AVOID
1. **DO NOT use OAuth2PasswordBearer** - the app uses HTTPBearer. Changing this breaks the frontend.
2. **DO NOT change the login response format** - frontend expects `{access_token, token_type, username}`.
3. **DO NOT modify credentials.yaml manually** - bcrypt hashes are sensitive to format.
4. **Build/flash operations are in-memory dicts** - they reset on server restart (by design).
5. **Board routes have NO auth** - only auth endpoints use `get_current_user` dependency.
6. **The `/api/boards/scan`, `/api/boards/status-log`, `/api/boards/discover`, and `/{board_name}/logs` paths must come BEFORE `/{board_name}`** in router registration - FastAPI matches routes in order.
7. **Frontend stores token in localStorage** - NOT cookies, NOT sessionStorage.
8. **CORS allows all origins** - needed for cross-origin requests during development.
9. **ESPHome build now supports companion files** - `yaml_file` + `companion_files` OR `.zip` archive.
10. **Arduino build backend already supports `libraries` param** - frontend now sends multi-file correctly.
11. **Board `mac_address` field is optional** - stored in boards.yaml, displayed on cards and flash selector.
12. **Password validation enforced on `create_user` and `change_password`** - `init_default_admin` uses `skip_validation=True` for the default `cactus123` password.
13. **`create_user()` now returns `Tuple[bool, str]`** instead of `bool` — callers must handle the error message.
14. **Board `last_seen` field is auto-updated** — on scan (if online) and on ping (if online). Stored as ISO timestamp in boards.yaml.
15. **Sensor data is auto-discovered during scan** — from ESPHome web_server page (HTML scraping + /events SSE fallback). Stored in boards.yaml per board.
16. **Status log uses YAML file** — `config/board_status_log.yaml` tracks online/offline transitions. Only logs when status changes. Auto-trims at 500 entries.
17. **MAC address auto-discovery** — during scan, if `web_online` and no MAC stored, tries to extract from ESPHome web page via regex.
18. **Frontend has 5 tabs** — Boards, Upload & Flash, Builds, Settings, Guide. The Guide tab is static HTML documentation.
19. **`install.sh` generates the systemd service file dynamically** — the `cactus-flasher.service` in the repo is a template. The installer writes the real one to `/etc/systemd/system/` with the correct user and paths.
20. **`deploy.sh` auto-detects paths** — uses `BASH_SOURCE` to find itself, `stat` to find the owner. No hardcoded paths.
21. **App can be installed in any directory** — `/opt`, `/home/user`, `/srv`, etc. The installer and deploy script adapt automatically.
22. **Board `web_username`/`web_password` fields** — optional HTTP Basic Auth credentials for ESPHome web_server. Stored in boards.yaml. Used by sensor discovery, MAC extraction, SSE log proxy, and OTA flash fallback.
23. **SSE log proxy endpoint** — `GET /api/boards/{name}/logs` proxies the board's `/events` SSE endpoint with auth. Frontend uses `EventSource` to stream live sensor/entity updates.
24. **OTA flash has web_server fallback** — `flash_firmware()` tries OTA port first, then falls back to `web_server_port /update` with HTTP Basic Auth if OTA port fails and web credentials are configured.
25. **VPS deployment uses Docker** — `network_mode: host`, port 8080, behind nginx reverse proxy at `flasher.atrichocity.cloud` with SSL. IONOS provider only allows ports 22, 80, 443.

## Running the App
```bash
cd /path/to/cactus-flasher
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Development Commands
```bash
# Activate venv (from project root)
source venv/bin/activate

# Install deps
pip install -r requirements.txt

# Fresh install on VPS (as root)
bash install.sh

# Deploy update (auto-detects paths)
bash deploy.sh

# Docker local dev
docker compose up --build
```

## TODO / Future Work
- Add auth protection to board/build/flash endpoints
- Add rate limiting
- Persistent build/flash history (database or file)
- WebSocket auth (currently unauthenticated)
- File size validation on uploads
- Cleanup of old builds/uploads
- ESPHome native API sensor discovery (requires `aioesphomeapi` + board API key)
- Force password change on first login with default credentials
- Auto-scan interval (periodic background scan for board status)
- Sensor history tracking (time-series data for charts)
- Board grouping / tagging for organization
- Edit board modal (currently must delete + re-add to change web credentials)
