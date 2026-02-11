# Cactus Flasher

ESP32 Web Flasher Application for OTA firmware updates.

## Features

- **Web-based OTA flashing** for ESP32 boards
- **Build support** for ESPHome, Arduino, and PlatformIO projects
- **Board management** with auto-discovery and status monitoring
- **Real-time progress** via WebSocket
- **Dark theme UI** with responsive design

## Quick Start

### Install Dependencies

```bash
cd /home/debian/cactus-flasher
pip install -r requirements.txt
```

### Run the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Default Login

- **Username**: admin
- **Password**: cactus123

## Network Topology

```
[VPS: cactus-flasher]
        |
        | DDNS: esp32gb.ddns.net
        v
[Home Router - Port Forwarding]
        |
        +-- Board XX: Webserver 80XX, OTA 82XX, API 60XX
        +-- Board 88 (cactus-sentinel): 8088, 8288, 6088
        +-- Board 01: 8001, 8201, 6001
        ...
```

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login and get JWT token
- `POST /api/auth/register` - Register new user (requires auth)
- `GET /api/auth/me` - Get current user info

### Boards
- `GET /api/boards` - List all boards
- `POST /api/boards` - Add new board
- `GET /api/boards/{name}` - Get board details
- `PUT /api/boards/{name}` - Update board
- `DELETE /api/boards/{name}` - Delete board
- `GET /api/boards/scan` - Scan all boards for status
- `POST /api/boards/{name}/ping` - Ping specific board

### Build
- `POST /api/build/esphome` - Build ESPHome firmware
- `POST /api/build/arduino` - Build Arduino firmware
- `POST /api/build/platformio` - Build PlatformIO firmware
- `GET /api/build/status/{id}` - Get build status
- `GET /api/build/logs/{id}` - Get build logs
- `GET /api/build/list` - List all builds

### Flash
- `POST /api/flash/upload` - Upload and flash binary
- `POST /api/flash/from-build` - Flash from build
- `GET /api/flash/status/{id}` - Get flash status
- `GET /api/flash/history` - Get flash history

### WebSocket
- `WS /ws` - Real-time updates for builds and flashes

## Configuration Files

### config/boards.yaml

```yaml
boards:
  cactus-sentinel:
    id: 88
    type: esp32
    host: null  # Uses default DDNS
```

### config/credentials.yaml

```yaml
users:
  admin:
    password_hash: $2b$12$...
    created_at: 2024-01-01T00:00:00
```

## Build Tools Setup

### ESPHome
```bash
pip install esphome
```

### Arduino CLI
```bash
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
arduino-cli core install esp32:esp32
```

### PlatformIO
```bash
pip install platformio
pio pkg install -g -p espressif32
```

## Production Deployment

### Nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name flasher.atrichocity.it;

    ssl_certificate /etc/letsencrypt/live/flasher.atrichocity.it/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/flasher.atrichocity.it/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Systemd Service

```ini
[Unit]
Description=Cactus Flasher
After=network.target

[Service]
User=debian
WorkingDirectory=/home/debian/cactus-flasher
ExecStart=/usr/local/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

## License

MIT License
