# Handover Document for Claude

**Date**: February 11, 2026
**Project**: Cactus Flasher
**Status**: Stable / Functional

## 1. Project Overview
Cactus Flasher is a web-based utility for managing and flashing ESP32 boards via OTA (Over-The-Air) updates. It uses a FastAPI backend and a vanilla JS frontend with Tailwind CSS.

### Key Features
- **Board Management**: Auto-discovery and manual addition of ESP32 boards.
- **Authentication**: JWT-based auth with `admin`/`cactus123` default credentials.
- **Flashing**: Upload `.bin` files or build from source (PlatformIO/Arduino/ESPHome) and flash via HTTP OTA.
- **Real-time Status**: WebSockets for build logs and flash progress.

## 2. Architecture
- **Backend**: Python FastAPI (`app/main.py`).
- **Frontend**: Single Page Application (`static/index.html`, `static/js/app.js`).
- **Services**:
  - `app/services/ota.py`: Handles the actual HTTP POST to ESP32 `/update` endpoint.
  - `app/services/scanner.py`: Scans network ports (82xx) to find boards.
  - `app/services/build.py`: Manages subprocess calls to build tools.
- **Configuration**:
  - `config/boards.yaml`: Registered boards.
  - `config/credentials.yaml`: User accounts (hashed passwords).

## 3. Current Status
- **Authentication**: Verified working.
- **Flashing**: Logic in `app/services/ota.py` is robust (MD5 checks, progress callbacks).
- **UI**: Functional, connects to WebSocket, handles auth tokens correctly.

## 4. Key Files to Review
- `app/main.py`: Entry point, WebSocket manager, Auth endpoints.
- `app/services/ota.py`: Core flashing logic.
- `app/routers/flash.py`: API endpoints for flashing.
- `static/js/app.js`: Frontend logic (Class `CactusFlasher`).

## 5. Restoration Instructions
A backup has been created: `cactus-flasher-backup-2026-02-11.tar.gz`.

To restore/setup on a new environment:
1.  **Extract**: `tar -xzf cactus-flasher-backup-2026-02-11.tar.gz`
2.  **Install dependencies**: `pip install -r requirements.txt`
3.  **Run**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## 6. Next Steps
- **Testing**: Verify physical flashing on actual hardware if available.
- **Build Tools**: Ensure `esphome`, `platformio`, and `arduino-cli` are installed in the environment if building from source is required.
- **Security**: Change default secret keys in `app/config.py` (or env vars) before production use.

## 7. Known Issues / Notes
- The `app/services/flash.py` file does not exist; logic is in `app/services/ota.py` and `app/routers/flash.py`.
- Boards are expected to expose:
  - Port `80xx`: Webserver
  - Port `82xx`: OTA
  - Port `60xx`: API
