# CLAUDE.md - Cactus Flasher Project Memory

## Project Overview
**Cactus Flasher** is an ESP32 Web Flasher application for OTA firmware updates.
- **Location**: `/home/debian/cactus-flasher`
- **Framework**: FastAPI (Python 3.13) + Vanilla JS frontend
- **VPS**: Debian, user `debian`, protected by Cactus Sentinel (fail2ban)
- **Backup**: `/home/debian/backups/cactus-flasher-backup-20260211-134223.tar.gz`
- **Status**: Auth flow WORKING and TESTED as of 2026-02-11

## CRITICAL - Do NOT Change These (Working Code)

### Authentication Flow (VERIFIED WORKING)
- **Library**: `python-jose[cryptography]` for JWT, `bcrypt` for password hashing
- **Security scheme**: `HTTPBearer` (NOT OAuth2PasswordBearer)
- **Token format**: `Authorization: Bearer <jwt_token>`
- **Login endpoint**: `POST /api/auth/login` - accepts JSON `{username, password}`, returns `{access_token, token_type, username}`
- **Token validation**: `GET /api/auth/me` - returns `{username}`
- **Default admin**: username `admin`, password `cactus123` (auto-created on first startup)
- **JWT config**: HS256 algorithm, 60 min expiry, secret key in `settings.SECRET_KEY`
- **Password storage**: bcrypt with 12 rounds, stored in `config/credentials.yaml`
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
      schemas.py         # Pydantic models (Login, Board, Build, Flash, WS)
    routers/
      __init__.py
      boards.py          # CRUD + scan + ping for boards
      build.py           # ESPHome/Arduino/PlatformIO compilation
      flash.py           # OTA firmware upload + flash
    services/
      __init__.py
      arduino.py         # arduino-cli compilation
      esphome.py         # ESPHome compilation
      platformio.py      # PlatformIO compilation
      ota.py             # HTTP OTA flash (multipart + chunked)
      scanner.py         # TCP/HTTP board scanning + discovery
  config/
    boards.yaml          # Board registry (name -> id, type, host)
    credentials.yaml     # User credentials (bcrypt hashes)
  static/
    index.html           # SPA with Tailwind CSS dark theme
    css/style.css        # Custom styles (cards, badges, animations)
    js/app.js            # CactusFlasher class (auth, boards, build, flash)
  venv/                  # Python virtual environment (Python 3.13)
  requirements.txt       # Dependencies
  README.md              # Full documentation
  CLAUDE.md              # THIS FILE
```

## API Routes Map
| Method | Path | Auth | Handler |
|--------|------|------|---------|
| POST | /api/auth/login | No | main.py:login |
| POST | /api/auth/register | Yes | main.py:register |
| GET | /api/auth/me | Yes | main.py:get_me |
| GET | /api/boards | No | boards.py:list_boards |
| POST | /api/boards | No | boards.py:create_board |
| GET | /api/boards/scan | No | boards.py:scan_boards |
| GET | /api/boards/discover | No | boards.py:discover_boards |
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
6. **The `/api/boards/scan` and `/api/boards/discover` paths must come BEFORE `/{board_name}`** in router registration - FastAPI matches routes in order.
7. **Frontend stores token in localStorage** - NOT cookies, NOT sessionStorage.
8. **CORS allows all origins** - needed for cross-origin requests during development.

## Running the App
```bash
cd /home/debian/cactus-flasher
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Development Commands
```bash
# Activate venv
source /home/debian/cactus-flasher/venv/bin/activate

# Install deps
pip install -r /home/debian/cactus-flasher/requirements.txt

# Create backup
tar -czf /home/debian/backups/cactus-flasher-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  --exclude='venv' --exclude='__pycache__' --exclude='.claude' \
  -C /home/debian cactus-flasher
```

## TODO / Future Work
- Add auth protection to board/build/flash endpoints
- Add rate limiting
- Persistent build/flash history (database or file)
- WebSocket auth (currently unauthenticated)
- File size validation on uploads
- Cleanup of old builds/uploads
