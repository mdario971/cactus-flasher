# Cactus Flasher

**ESP32 Web Flasher** — OTA firmware updates from a web dashboard.

Built with Python 3.13 / FastAPI + Vanilla JS (Tailwind CSS dark theme).

- **Web-based OTA flashing** for ESP32 boards over HTTP
- **Build support** for ESPHome, Arduino CLI, and PlatformIO projects
- **Board management** with network scanning, auto-discovery, and status monitoring
- **Multi-file uploads** — ESPHome YAML + companions, Arduino sketches + libraries
- **User management** with JWT authentication and password security
- **Real-time progress** via WebSocket
- **MAC address tracking** and sensor discovery

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [VPS Debian — Fresh Installation](#2-vps-debian--fresh-installation)
3. [Deploying Updates (Existing VPS)](#3-deploying-updates-existing-vps)
4. [Files: Deployed vs. Preserved](#4-files-deployed-vs-preserved)
5. [Systemd Service Management](#5-systemd-service-management)
6. [Docker Deployment (Alternative)](#6-docker-deployment-alternative)
7. [Windows Development Setup](#7-windows-development-setup)
8. [Configuration Reference](#8-configuration-reference)
9. [Default Login & First Steps](#9-default-login--first-steps)
10. [API Reference](#10-api-reference)
11. [Build Tools Setup (Optional)](#11-build-tools-setup-optional)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Architecture Overview

### Network Topology

```
VPS (cactus-flasher on port 8000)
  |
  |  Nginx reverse proxy (443 SSL → 127.0.0.1:8000)
  |
  |  DDNS: esp32gb.ddns.net
  v
Home Router (port forwarding per board)
  |
  +-- Board 01: Webserver 8001, OTA 8201, API 6001
  +-- Board 88 (cactus-sentinel): 8088, 8288, 6088
  +-- Board XX: 80XX, 82XX, 60XX
```

**Board port convention** — Board ID `XX` (01–99) maps to:
| Port Type | Formula | Example (ID 88) |
|-----------|---------|------------------|
| Webserver | `80XX`  | `8088`           |
| OTA       | `82XX`  | `8288`           |
| Native API| `60XX`  | `6088`           |

### Project Structure

```
cactus-flasher/
├── app/
│   ├── main.py              # FastAPI app, auth endpoints, WebSocket
│   ├── auth.py              # JWT + bcrypt authentication
│   ├── config.py            # Settings, YAML config loader
│   ├── models/schemas.py    # Pydantic request/response models
│   ├── routers/
│   │   ├── boards.py        # Board CRUD, scan, ping, status log
│   │   ├── build.py         # ESPHome/Arduino/PlatformIO compilation
│   │   └── flash.py         # OTA firmware upload + flash
│   └── services/
│       ├── scanner.py       # TCP/HTTP board scanning + discovery
│       ├── ota.py           # HTTP OTA flash (multipart + chunked)
│       ├── esphome.py       # ESPHome compilation
│       ├── arduino.py       # arduino-cli compilation
│       ├── platformio.py    # PlatformIO compilation
│       ├── sensors.py       # ESPHome web_server sensor scraping
│       └── status_logger.py # Board online/offline status log
├── static/
│   ├── index.html           # SPA (5 tabs: Boards, Upload, Builds, Settings, Guide)
│   ├── css/style.css        # Custom styles, animations, tooltips
│   └── js/app.js            # CactusFlasher frontend class
├── config/
│   ├── boards.yaml          # Board registry (name, id, type, host, mac)
│   ├── credentials.yaml     # User credentials — bcrypt hashes (gitignored)
│   └── board_status_log.yaml# Online/offline transition log (auto-created)
├── cactus-flasher.service   # Systemd unit file
├── deploy.sh                # Deploy/rollback script
├── Dockerfile               # Python 3.13-slim image
├── docker-compose.yml       # Local development (hot reload)
├── docker-compose.prod.yml  # Production Docker (optional)
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
└── CLAUDE.md                # AI assistant project memory
```

---

## 2. VPS Debian — Fresh Installation

These steps install Cactus Flasher on a clean Debian VPS from scratch.

### 2.1 System Prerequisites

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx
```

### 2.2 Clone the Repository

```bash
cd /home/debian
git clone https://github.com/mdario971/cactus-flasher.git
cd cactus-flasher
```

> If the repo is private, use a GitHub personal access token or SSH key.

### 2.3 Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.4 Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and set a strong `SECRET_KEY`:

```bash
# Generate a random secret key
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into `.env`:

```env
SECRET_KEY=<your-generated-secret-key>
DDNS_HOST=esp32gb.ddns.net
```

### 2.5 Create Runtime Directories

```bash
mkdir -p config uploads builds /home/debian/backups
```

### 2.6 Set File Permissions

```bash
# Ensure debian user owns everything
sudo chown -R debian:debian /home/debian/cactus-flasher

# Application files
chmod -R 755 app/ static/
chmod 644 requirements.txt

# Writable runtime directories
chmod 755 config/ uploads/ builds/

# Sensitive files
chmod 600 .env
chmod 755 deploy.sh

# credentials.yaml will be auto-created on first run
# Once created, lock it down:
# chmod 600 config/credentials.yaml
```

### 2.7 Install Systemd Service

```bash
sudo cp cactus-flasher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cactus-flasher
sudo systemctl start cactus-flasher
```

Verify it's running:

```bash
sudo systemctl status cactus-flasher
curl -s http://127.0.0.1:8000/api/auth/me | head
```

### 2.8 Configure Nginx Reverse Proxy

Create `/etc/nginx/sites-available/cactus-flasher`:

```nginx
server {
    listen 80;
    server_name flasher.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and get SSL:

```bash
sudo ln -s /etc/nginx/sites-available/cactus-flasher /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Get SSL certificate (replace with your domain)
sudo certbot --nginx -d flasher.yourdomain.com
```

### 2.9 Verify Installation

```bash
# Check service is running
sudo systemctl status cactus-flasher

# Check app responds
curl -s https://flasher.yourdomain.com/ | head -5

# Check default admin was created
ls -la config/credentials.yaml
```

Open `https://flasher.yourdomain.com` in your browser and log in with the [default credentials](#9-default-login--first-steps).

---

## 3. Deploying Updates (Existing VPS)

When the VPS already has Cactus Flasher installed, use `deploy.sh` to safely update. The script **always creates a backup before making changes**, so you can roll back if something goes wrong.

### How deploy.sh Works

1. Creates a timestamped backup tarball in `/home/debian/backups/`
2. Pulls the requested version from git (latest main, specific tag, or previous tag)
3. Installs/updates pip dependencies
4. Restarts the systemd service
5. Verifies the service is healthy

The backup **excludes** `venv/`, `__pycache__/`, `uploads/`, and `builds/` (large/regenerable directories) but **includes** everything else — `app/`, `static/`, `config/`, `.env`, etc.

### Usage

```bash
cd /home/debian/cactus-flasher

# Deploy latest from main branch
bash deploy.sh

# Deploy a specific version tag
bash deploy.sh v2.0.0

# Rollback to the previous version tag
bash deploy.sh rollback
```

### Manual Backup (Extra Safety)

Before a major update, you can create a manual backup:

```bash
tar -czf /home/debian/backups/cactus-flasher-manual-$(date +%Y%m%d-%H%M%S).tar.gz \
    --exclude='venv' --exclude='__pycache__' --exclude='.claude' \
    -C /home/debian cactus-flasher
```

### Restoring from Backup

If `deploy.sh rollback` isn't enough (e.g., you need to restore config files):

```bash
# Stop the service
sudo systemctl stop cactus-flasher

# List available backups
ls -lt /home/debian/backups/

# Restore a specific backup
cd /home/debian
tar -xzf /home/debian/backups/pre-deploy-20260215-143000.tar.gz

# Restart the service
sudo systemctl start cactus-flasher
```

### Updating the Systemd Service File

If `cactus-flasher.service` changed in the update:

```bash
sudo cp /home/debian/cactus-flasher/cactus-flasher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart cactus-flasher
```

---

## 4. Files: Deployed vs. Preserved

Understanding which files get overwritten on update and which are preserved is critical for safe deployments.

### Deployed (Overwritten on `git pull`)

These files come from the git repository and are replaced on every update:

| Path | Description |
|------|-------------|
| `app/` | All Python application code |
| `static/` | Frontend HTML, CSS, JS |
| `requirements.txt` | Python dependencies |
| `deploy.sh` | Deploy/rollback script |
| `Dockerfile` | Docker image definition |
| `docker-compose.yml` | Local dev Docker config |
| `docker-compose.prod.yml` | Production Docker config |
| `cactus-flasher.service` | Systemd unit file (must be copied to `/etc/systemd/system/`) |
| `.env.example` | Environment variable template |
| `config/boards.yaml` | Board registry (in repo as seed data) |
| `CLAUDE.md` | AI assistant memory |

### Preserved (Never Overwritten)

These files are **gitignored** and survive deployments:

| Path | Description | Created |
|------|-------------|---------|
| `.env` | Secret key, DDNS host, tool paths | Manually from `.env.example` |
| `config/credentials.yaml` | User accounts (bcrypt hashes) | Auto on first startup |
| `config/board_status_log.yaml` | Board online/offline history | Auto on first scan |
| `uploads/` | Uploaded firmware files | At runtime |
| `builds/` | Build artifacts | At runtime |
| `venv/` | Python virtual environment | During setup |

### File Permissions Reference

```
/home/debian/cactus-flasher/          # 755 debian:debian
├── app/                               # 755 — application code
├── static/                            # 755 — frontend files
├── config/                            # 755 — YAML configs
│   ├── boards.yaml                    # 644 — board registry
│   ├── credentials.yaml               # 600 — user passwords (sensitive)
│   └── board_status_log.yaml          # 644 — status log
├── uploads/                           # 755 — firmware uploads
├── builds/                            # 755 — build artifacts
├── venv/                              # 755 — Python venv
├── .env                               # 600 — secrets (sensitive)
├── requirements.txt                   # 644 — dependencies
├── deploy.sh                          # 755 — deploy script (executable)
└── cactus-flasher.service             # 644 — systemd unit
```

> **Note on `config/boards.yaml`**: The repo ships a seed file with one example board. On a running VPS, this file will contain your actual board registry. A `git pull` will attempt to overwrite it. The `deploy.sh` script creates a backup first, but if you want extra safety, back up `config/boards.yaml` manually before deploying, or add it to `.gitignore` on the VPS.

---

## 5. Systemd Service Management

The recommended production deployment uses systemd with a Python venv (no Docker needed).

### Service Commands

```bash
# Start / Stop / Restart
sudo systemctl start cactus-flasher
sudo systemctl stop cactus-flasher
sudo systemctl restart cactus-flasher

# Check status
sudo systemctl status cactus-flasher

# View logs (live tail)
sudo journalctl -u cactus-flasher -f

# View last 50 log lines
sudo journalctl -u cactus-flasher -n 50

# Enable at boot
sudo systemctl enable cactus-flasher
```

### Security Hardening

The service file includes these security features:

| Directive | Purpose |
|-----------|---------|
| `NoNewPrivileges=yes` | Prevents the process from gaining new privileges |
| `ProtectSystem=strict` | Makes the entire filesystem read-only |
| `ProtectHome=read-only` | Makes `/home` read-only |
| `ReadWritePaths=...` | Explicitly allows writes to `config/`, `uploads/`, `builds/` |
| `PrivateTmp=yes` | Gives the service its own `/tmp` directory |

The app binds to `127.0.0.1:8000` (localhost only) — Nginx handles external access with SSL.

---

## 6. Docker Deployment (Alternative)

If you prefer Docker over systemd+venv, use the production Docker Compose file.

### Production Docker

```bash
cd /home/debian/cactus-flasher

# Copy and edit environment file
cp .env.example .env
nano .env  # Set SECRET_KEY

# Start in background
docker compose -f docker-compose.prod.yml up -d --build

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Stop
docker compose -f docker-compose.prod.yml down

# Update (pull latest code, rebuild)
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build
```

The production Docker config:
- Binds to `127.0.0.1:8000` (use Nginx in front for SSL)
- Mounts `config/`, `uploads/`, `builds/` as persistent volumes
- Reads `.env` file for secrets
- Auto-restarts on failure
- Limits log file size to 10MB (3 files rotation)

### Persistent Data Volumes

| Container Path | Host Path | Purpose |
|----------------|-----------|---------|
| `/app/config` | `./config` | Board registry, credentials |
| `/app/uploads` | `./uploads` | Uploaded firmware files |
| `/app/builds` | `./builds` | Build artifacts |

---

## 7. Windows Development Setup

Develop and test locally on Windows using Docker and VS Code.

### Prerequisites

1. **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) (enable WSL 2 backend)
2. **VS Code** — [code.visualstudio.com](https://code.visualstudio.com/)
3. **Git** — [git-scm.com](https://git-scm.com/)

### Setup

```bash
# Clone the repository
git clone https://github.com/mdario971/cactus-flasher.git
cd cactus-flasher

# Create environment file
copy .env.example .env
# Edit .env and set SECRET_KEY (any value is fine for local dev)
```

### Run with Docker (Hot Reload)

```bash
docker compose up --build
```

This starts the app at **http://localhost:8000** with:
- Hot reload — edit `app/` or `static/` files and the server restarts automatically
- Volume mounts — your local files are synced into the container
- Dev secret key — pre-configured for local development

To stop: press `Ctrl+C` or run `docker compose down`.

### VS Code Debug Configuration

The project includes `.vscode/launch.json` for debugging without Docker:

1. Open the project in VS Code
2. Create a local Python venv:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Press **F5** to start debugging — this launches uvicorn with `--reload` on port 8000
4. Set breakpoints in any Python file

The `.vscode/settings.json` configures:
- Python interpreter path (`venv/Scripts/python.exe`)
- Auto-format on save
- Auto-organize imports
- Hidden files: `__pycache__`, `venv`, `.claude`

### Docker Commands Reference

```bash
# Build and start
docker compose up --build

# Start in background
docker compose up -d --build

# View logs
docker compose logs -f

# Stop and remove containers
docker compose down

# Rebuild from scratch (after Dockerfile changes)
docker compose down && docker compose up --build
```

---

## 8. Configuration Reference

### Environment Variables (`.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | **Yes** | `cactus-flasher-secret-key-change-in-production` | JWT signing secret — **must change in production** |
| `DDNS_HOST` | No | `esp32gb.ddns.net` | DDNS hostname for board resolution |
| `ESPHOME_PATH` | No | `esphome` | Path to ESPHome binary |
| `ARDUINO_CLI_PATH` | No | `arduino-cli` | Path to Arduino CLI binary |
| `PLATFORMIO_PATH` | No | `pio` | Path to PlatformIO binary |
| `APP_PORT` | No | `8000` | Server port (used by docker-compose) |

Generate a strong `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Board Registry (`config/boards.yaml`)

```yaml
boards:
  cactus-sentinel:
    id: 88
    type: esp32
    host: null          # null = auto-generate from DDNS_HOST
    mac_address: null    # Optional, auto-discovered during scan
    last_seen: null      # Auto-updated on scan/ping
    sensors: {}          # Auto-discovered from ESPHome web_server
```

**Board hostname auto-generation**: strips `cactus-`/`esp32-`/`esp-` prefix, then formats as `{shortname}-{ID:02d}.{DDNS_HOST}`. Example: `cactus-sentinel` ID 88 becomes `sentinel-88.esp32gb.ddns.net`.

### User Credentials (`config/credentials.yaml`)

Auto-created on first startup. **Do not edit manually** — use the Settings UI or API.

```yaml
users:
  admin:
    password_hash: $2b$12$...    # bcrypt hash
    created_at: '2026-02-11T...'
    password_changed_at: null
```

### Password Policy

Passwords must meet all of these requirements:
- Minimum 8 characters
- At least 1 uppercase letter (A-Z)
- At least 1 lowercase letter (a-z)
- At least 1 digit (0-9)
- At least 1 special character (`!@#$%^&*()_+-=[]{}` etc.)

---

## 9. Default Login & First Steps

On first startup, a default admin account is created automatically:

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `cactus123` |

> **Change the default password immediately** via Settings > User Management > Change Password. The default password `cactus123` does not meet the password policy — it is only accepted during auto-creation.

### First Steps After Installation

1. Open the web UI and log in with the default credentials
2. Go to **Settings** tab > **Change Password** and set a strong password
3. Go to **Settings** tab > **Board Management** and add your ESP32 boards
4. Go to **Boards** tab and click **Scan** to check board connectivity
5. Go to **Upload & Flash** tab to upload and flash firmware

---

## 10. API Reference

All endpoints return JSON. Authentication uses JWT Bearer tokens — include `Authorization: Bearer <token>` in request headers.

### Authentication

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/api/auth/login` | No | Login, returns `{access_token, token_type, username}` |
| `POST` | `/api/auth/register` | Yes | Register new user |
| `GET` | `/api/auth/me` | Yes | Get current user info |
| `GET` | `/api/auth/users` | Yes | List all users |
| `PUT` | `/api/auth/change-password` | Yes | Change own password |
| `DELETE` | `/api/auth/users/{username}` | Yes | Delete user (cannot delete self or last user) |

### Boards

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `GET` | `/api/boards` | No | List all boards |
| `POST` | `/api/boards` | No | Add new board |
| `GET` | `/api/boards/scan` | No | Scan all boards for status |
| `GET` | `/api/boards/status-log` | No | Get board status transition log |
| `GET` | `/api/boards/discover` | No | Auto-discover boards on network |
| `GET` | `/api/boards/{name}` | No | Get board details |
| `PUT` | `/api/boards/{name}` | No | Update board |
| `DELETE` | `/api/boards/{name}` | No | Delete board |
| `POST` | `/api/boards/{name}/ping` | No | Ping specific board |

### Build

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/api/build/esphome` | No | Build ESPHome firmware (YAML + companions or ZIP) |
| `POST` | `/api/build/arduino` | No | Build Arduino firmware (sketch + libraries) |
| `POST` | `/api/build/platformio` | No | Build PlatformIO firmware (ZIP project) |
| `GET` | `/api/build/status/{id}` | No | Get build status |
| `GET` | `/api/build/logs/{id}` | No | Get build logs |
| `GET` | `/api/build/list` | No | List all builds |

### Flash

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/api/flash/upload` | No | Upload and flash binary firmware |
| `POST` | `/api/flash/from-build` | No | Flash firmware from a completed build |
| `GET` | `/api/flash/status/{id}` | No | Get flash operation status |
| `GET` | `/api/flash/history` | No | Get flash history |

### WebSocket

| Protocol | Path | Description |
|----------|------|-------------|
| `WS` | `/ws` | Real-time updates for builds, flashes, and scans |

Interactive API docs available at `/docs` (Swagger UI).

---

## 11. Build Tools Setup (Optional)

These are only needed if you use the build feature (compile firmware on the server).

### ESPHome

```bash
source venv/bin/activate
pip install esphome
```

### Arduino CLI

```bash
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
sudo mv bin/arduino-cli /usr/local/bin/
arduino-cli core install esp32:esp32
```

### PlatformIO

```bash
source venv/bin/activate
pip install platformio
pio pkg install -g -p espressif32
```

---

## 12. Troubleshooting

### Service Won't Start

```bash
# Check the logs for errors
sudo journalctl -u cactus-flasher -n 50

# Common causes:
# - Missing .env file → cp .env.example .env
# - Missing venv → python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
# - Wrong permissions → sudo chown -R debian:debian /home/debian/cactus-flasher
```

### Permission Denied Errors

```bash
# Fix ownership
sudo chown -R debian:debian /home/debian/cactus-flasher

# Fix credentials file permissions
chmod 600 config/credentials.yaml
chmod 600 .env

# Fix runtime directories
chmod 755 config/ uploads/ builds/
```

### Port Already in Use

```bash
# Find what's using port 8000
sudo lsof -i :8000

# Kill the process if needed
sudo kill <PID>
```

### Docker Container Won't Start

```bash
# Check container logs
docker compose logs

# Remove old container and rebuild
docker compose down
docker compose up --build
```

### Rollback After Failed Deploy

```bash
# Option 1: Use deploy.sh rollback (reverts to previous git tag)
bash deploy.sh rollback

# Option 2: Restore from backup tarball
sudo systemctl stop cactus-flasher
ls -lt /home/debian/backups/     # Find the backup you want
cd /home/debian
tar -xzf /home/debian/backups/pre-deploy-YYYYMMDD-HHMMSS.tar.gz
sudo systemctl start cactus-flasher
```

### Reset Admin Password

If you've lost access, delete the credentials file and restart:

```bash
sudo systemctl stop cactus-flasher
rm config/credentials.yaml
sudo systemctl start cactus-flasher
# Default admin/cactus123 will be recreated
```

---

## License

MIT License
