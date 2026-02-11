# Cactus Flasher - Architecture Documentation

**Last verified**: 2026-02-11 | **Version**: 1.0.0 | **Auth flow**: WORKING

---

## 1. System Architecture

```
                    +-------------------+
                    |   Web Browser     |
                    | (static/index.html|
                    |  + app.js)        |
                    +--------+----------+
                             |
                     HTTPS / WSS
                             |
                    +--------v----------+
                    |   Nginx (reverse  |
                    |   proxy :443)     |
                    +--------+----------+
                             |
                    HTTP :8000 / WS
                             |
                    +--------v----------+
                    |   FastAPI App     |
                    |   (app/main.py)   |
                    +--------+----------+
                             |
              +--------------+--------------+
              |              |              |
    +---------v--+  +--------v---+  +------v-------+
    | Auth Module|  | Routers    |  | WebSocket    |
    | (auth.py)  |  | boards.py  |  | Manager      |
    |            |  | build.py   |  | (main.py)    |
    |            |  | flash.py   |  |              |
    +------------+  +-----+------+  +--------------+
                          |
              +-----------+-----------+
              |           |           |
    +---------v-+ +-------v--+ +-----v------+
    | Services  | | Services | | Services   |
    | arduino.py| | esphome  | | ota.py     |
    |           | | .py      | | scanner.py |
    +-----------+ +----------+ +------------+
              |           |           |
              v           v           v
        [arduino-cli] [esphome]  [ESP32 boards
         subprocess   subprocess  via HTTP OTA]
```

## 2. Authentication System (VERIFIED WORKING)

### 2.1 Backend Implementation (`app/auth.py`)

**Security Scheme**: `HTTPBearer` (FastAPI's built-in)
- This extracts `Authorization: Bearer <token>` header automatically
- DO NOT change to `OAuth2PasswordBearer` - it breaks the frontend

**Password Hashing**: `bcrypt` with 12 salt rounds
- `hash_password(password)` -> bcrypt hash string
- `verify_password(plain, hashed)` -> bool
- Stored in `config/credentials.yaml` under `users.<username>.password_hash`

**JWT Tokens**: `python-jose` library
- Algorithm: HS256
- Expiry: 60 minutes (configurable via `settings.ACCESS_TOKEN_EXPIRE_MINUTES`)
- Payload: `{"sub": "<username>", "exp": <timestamp>}`
- Secret: `settings.SECRET_KEY` (env var `SECRET_KEY` or default)

### 2.2 Auth Endpoints (defined in `app/main.py`, NOT in a router)

```
POST /api/auth/login
  Request:  {"username": "admin", "password": "cactus123"}
  Response: {"access_token": "eyJ...", "token_type": "bearer", "username": "admin"}
  Auth: None required

POST /api/auth/register
  Request:  {"username": "new_user", "password": "pass123"}
  Response: {"message": "User new_user created successfully"}
  Auth: Bearer token required (only logged-in users can create new users)

GET /api/auth/me
  Response: {"username": "admin"}
  Auth: Bearer token required
```

### 2.3 Frontend Auth Flow (`static/js/app.js`)

```
1. Page Load
   |
   +-> Token in localStorage?
       |
       +-- YES -> GET /api/auth/me (with Bearer token)
       |          |
       |          +-- 200 OK -> showApp() (load boards, connect WS)
       |          +-- 401    -> logout() (clear storage, show login)
       |
       +-- NO  -> showLogin() (show modal)

2. Login Submit
   |
   +-> POST /api/auth/login {username, password}
       |
       +-- 200 OK -> store token+username in localStorage -> showApp()
       +-- 401    -> show error message in modal

3. API Calls (all go through this.api() method)
   |
   +-> Adds Authorization: Bearer <token> header
   +-> On 401 response -> automatic logout()
```

### 2.4 Default Admin
- On first startup, `init_default_admin()` creates user `admin` / `cactus123`
- Only runs if `credentials.yaml` has no users
- Called in FastAPI lifespan handler

## 3. Board Management System

### 3.1 Port Convention
```
Board ID XX (01-99):
  Webserver port = 8000 + XX
  OTA port       = 8200 + XX
  API port       = 6000 + XX

Example: Board ID 88 (cactus-sentinel)
  Webserver: 8088
  OTA:       8288
  API:       6088
```

### 3.1.1 Hostname Convention
- Auto-generated from board name: strip `cactus-`/`esp32-`/`esp-` prefix, format `{shortname}-{ID:02d}.{DDNS_HOST}`
- Example: `cactus-sentinel` ID 88 -> `sentinel-88.esp32gb.ddns.net`
- Custom hostname can override via `hostname` field in `boards.yaml`

### 3.2 Board Config (`config/boards.yaml`)
```yaml
boards:
  <board-name>:
    id: <int 1-99>
    type: <esp32|esp32s2|esp32s3|esp32c3|esp8266>
    host: <string|null>      # null = use default DDNS
    hostname: <string|null>  # null = auto-generated
```

### 3.3 Board Scanner (`app/services/scanner.py`)
- `scan_board()` - TCP connection test to OTA port
- `scan_board_http()` - HTTP GET to webserver port
- `scan_all_boards()` - concurrent scan of all registered boards
- `discover_boards_on_network()` - port range scan (8201-8299), accepts `known_board_ids` to flag new boards

### 3.4 Discovery Endpoint (`GET /api/boards/discover`)
- Scans OTA ports 8201-8299 on DDNS host
- `?auto_register=true` auto-adds new boards as `board-XX` to boards.yaml
- Returns: `{discovered, total_found, new_boards, auto_registered}`
- Route must be registered BEFORE `/{board_name}` to avoid path conflict

## 4. Build System

### 4.1 Build Pipeline
```
Upload File -> Save to uploads/<build_id>/ -> Background Task -> Compile -> Save to builds/<build_id>/firmware.bin
```

### 4.2 Supported Build Types

| Type | Endpoint | Input | Tool |
|------|----------|-------|------|
| ESPHome | POST /api/build/esphome | .yaml file | esphome CLI |
| Arduino | POST /api/build/arduino | .ino file | arduino-cli |
| PlatformIO | POST /api/build/platformio | .zip project | pio CLI |

### 4.3 Build Status Tracking
- In-memory dict `build_operations: dict[str, BuildStatus]`
- States: `pending` -> `building` -> `success` / `failed`
- Resets on server restart (by design, no persistence)

## 5. Flash (OTA) System

### 5.1 Flash Pipeline
```
Firmware .bin -> HTTP POST to http://<host>:<ota_port>/update -> ESP32 reboots
```

### 5.2 OTA Protocol
- Standard ESP32 HTTP OTA update endpoint (`/update`)
- Multipart form upload with `x-MD5` header for verification
- Also supports chunked transfer for progress tracking
- Timeout: 120 seconds

### 5.3 Flash Status Tracking
- In-memory dict `flash_operations: dict[str, FlashStatus]`
- States: `pending` -> `uploading` -> `success` / `failed`
- Progress callback updates percentage in real-time

## 6. WebSocket System

### 6.1 Connection Manager (`app/main.py`)
- `ConnectionManager` class manages active WebSocket connections
- `connect()`, `disconnect()`, `broadcast()`, `send_to()`
- Endpoint: `WS /ws` (unauthenticated)

### 6.2 Message Types
```json
{"type": "ping"}           // Client -> Server (keepalive)
{"type": "pong"}           // Server -> Client (response)
{"type": "log", "data": {"message": "...", "level": "info"}}
{"type": "progress", "data": {"percent": 50, "message": "..."}}
{"type": "status", "data": {"board": "..."}}
```

## 7. Frontend Architecture (`static/js/app.js`)

### 7.1 CactusFlasher Class
Single class handles everything:
- `init()` -> `setupEventListeners()` + auth check
- `api(endpoint, options)` -> fetch wrapper with auth headers
- `login()` / `logout()` / `validateToken()`
- `loadBoards()` / `scanBoards()` / `pingBoard()` / `deleteBoard()` / `addBoard()`
- `flashFirmware()` -> handles binary upload OR build-then-flash
- `waitForBuild()` / `waitForFlash()` -> polling loops
- `connectWebSocket()` -> auto-reconnect on disconnect

### 7.2 UI Structure
- Login modal (shown when unauthenticated)
- Header with username + logout button
- 4 tabs: Boards | Upload & Flash | Builds | Settings
- Add Board modal (popup)
- Console panel with progress bar
- Toast notifications

### 7.3 Styling
- Tailwind CSS (CDN) with custom dark theme
- Custom color palette: `cactus-50` to `cactus-900` (green shades)
- Custom CSS in `static/css/style.css` for scrollbars, animations, badges

## 8. Data Models (`app/models/schemas.py`)

### Enums
- `ProjectType`: esphome, arduino, platformio
- `BoardType`: esp32, esp32s2, esp32s3, esp32c3, esp8266

### Auth Models
- `LoginRequest`: username, password
- `LoginResponse`: access_token, token_type="bearer", username
- `UserCreate`: username, password

### Board Models
- `BoardBase/Create`: name, id (1-99), type, host?, hostname?
- `BoardUpdate`: name?, type?, host?, hostname?
- `BoardStatus`: name, id, type, ports, online, host, hostname
- `BoardList`: list of BoardStatus

### Build Models
- `BuildRequest`: project_type, board_type
- `BuildStatus`: build_id, status, message?, firmware_path?, logs?

### Flash Models
- `FlashRequest`: board_name, firmware_path?, build_id?
- `FlashStatus`: flash_id, board_name, status, progress, message?

### WebSocket
- `WSMessage`: type (log|progress|status|error), data dict

## 9. Configuration (`app/config.py`)

### Directory Structure
- `BASE_DIR`: `/home/debian/cactus-flasher`
- `CONFIG_DIR`: `<base>/config`
- `UPLOADS_DIR`: `<base>/uploads` (auto-created)
- `BUILDS_DIR`: `<base>/builds` (auto-created)

### Settings Class
| Setting | Env Var | Default |
|---------|---------|---------|
| SECRET_KEY | SECRET_KEY | cactus-flasher-secret-key-change-in-production |
| ALGORITHM | - | HS256 |
| ACCESS_TOKEN_EXPIRE_MINUTES | - | 60 |
| DDNS_HOST | DDNS_HOST | esp32gb.ddns.net |
| ESPHOME_PATH | ESPHOME_PATH | esphome |
| ARDUINO_CLI_PATH | ARDUINO_CLI_PATH | arduino-cli |
| PLATFORMIO_PATH | PLATFORMIO_PATH | pio |

## 10. Deployment Notes

### Run in Development
```bash
cd /home/debian/cactus-flasher
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run in Production
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
# Behind nginx reverse proxy with SSL
```

### Nginx Config
- SSL termination at nginx
- WebSocket upgrade support required (`Upgrade` + `Connection` headers)
- Domain: `flasher.atrichocity.it`

### Systemd Service
- User: debian
- WorkingDirectory: /home/debian/cactus-flasher
- Restart: always
