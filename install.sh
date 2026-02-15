#!/usr/bin/env bash
# Cactus Flasher - Interactive Installer
# Run as root on Debian 12:
#   bash install.sh
#
# Installs in the CURRENT directory: $(pwd)/cactus-flasher
# Asks for the system user to run the service.

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}  🌵 Cactus Flasher — Installer${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

log_step() { echo -e "\n${GREEN}==>${NC} ${BOLD}$1${NC}"; }
log_info() { echo -e "    ${CYAN}$1${NC}"; }
log_warn() { echo -e "    ${YELLOW}⚠ $1${NC}"; }
log_error() { echo -e "    ${RED}✗ $1${NC}"; }
log_ok() { echo -e "    ${GREEN}✓ $1${NC}"; }

# ─── Root check ───────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    log_error "This script must be run as root."
    echo "    Usage: sudo bash install.sh"
    exit 1
fi

print_header

# ─── Installation directory ───────────────────────────────────
# If running from inside the repo (install.sh exists here), use current dir
# Otherwise, clone into a new subdirectory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/app/main.py" ] && [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    # Running from inside the repo
    INSTALL_DIR="$SCRIPT_DIR"
    ALREADY_CLONED=true
else
    # Running from parent directory — will clone repo
    INSTALL_DIR="$(pwd)/cactus-flasher"
    ALREADY_CLONED=false
fi

echo -e "${BOLD}Installation directory:${NC} ${CYAN}$INSTALL_DIR${NC}"
echo ""

# ─── Ask for username ─────────────────────────────────────────
echo -e "${BOLD}Which system user should run Cactus Flasher?${NC}"
echo ""

# Show existing non-root users
EXISTING_USERS=$(awk -F: '$3 >= 1000 && $3 < 65534 && $7 !~ /nologin|false/ {print $1}' /etc/passwd || true)
if [ -n "$EXISTING_USERS" ]; then
    echo "  Existing users:"
    for u in $EXISTING_USERS; do
        echo -e "    ${CYAN}→ $u${NC}"
    done
    echo ""
fi

read -rp "  Enter username [default: debian]: " APP_USER
APP_USER="${APP_USER:-debian}"

# Validate username
if ! [[ "$APP_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    log_error "Invalid username: '$APP_USER'. Use lowercase letters, digits, hyphens, underscores."
    exit 1
fi

APP_DIR="$INSTALL_DIR"
BACKUP_DIR="$(dirname "$INSTALL_DIR")/cactus-flasher-backups"
SERVICE_NAME="cactus-flasher"

echo ""
echo -e "${BOLD}Installation summary:${NC}"
echo -e "  User:          ${CYAN}$APP_USER${NC}"
echo -e "  App directory:  ${CYAN}$APP_DIR${NC}"
echo -e "  Backups:        ${CYAN}$BACKUP_DIR${NC}"
echo -e "  Service:        ${CYAN}$SERVICE_NAME${NC}"
echo ""
read -rp "  Continue? [Y/n]: " CONFIRM
CONFIRM="${CONFIRM:-Y}"
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# ─── Step 1: Create user if needed ───────────────────────────
log_step "Step 1/8: System user"

if id "$APP_USER" &>/dev/null; then
    log_ok "User '$APP_USER' already exists"
else
    useradd -m -s /bin/bash "$APP_USER"
    log_ok "Created user '$APP_USER'"
fi

# ─── Step 2: Install system packages ─────────────────────────
log_step "Step 2/8: System packages"

apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx > /dev/null 2>&1
log_ok "Installed: python3, python3-venv, git, nginx, certbot"

# ─── Step 3: Clone or update repository ──────────────────────
log_step "Step 3/8: Repository"

REPO_URL="https://github.com/mdario971/cactus-flasher.git"

if [ "$ALREADY_CLONED" = true ]; then
    # Already running from inside the repo
    if [ -d "$APP_DIR/.git" ]; then
        log_info "Running from repo directory, pulling latest..."
        cd "$APP_DIR"
        git fetch origin 2>/dev/null || true
        git checkout main 2>/dev/null || true
        git pull origin main 2>/dev/null || true
        log_ok "Updated to latest main"
    else
        log_ok "Using current directory (not a git repo — skipping pull)"
    fi
elif [ -d "$APP_DIR/.git" ]; then
    log_info "Repository already exists, pulling latest..."
    cd "$APP_DIR"
    git fetch origin 2>/dev/null || true
    git checkout main 2>/dev/null || true
    git pull origin main 2>/dev/null || true
    log_ok "Updated to latest main"
else
    if [ -d "$APP_DIR" ]; then
        # Directory exists but is not a git repo — back it up
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        log_warn "Directory $APP_DIR exists but is not a git repo"
        log_info "Backing up to ${APP_DIR}-old-${TIMESTAMP}..."
        mv "$APP_DIR" "${APP_DIR}-old-${TIMESTAMP}"
    fi

    log_info "Cloning from $REPO_URL..."

    if git clone "$REPO_URL" "$APP_DIR" 2>/dev/null; then
        log_ok "Cloned repository"
    else
        log_warn "Clone failed (private repo?). Trying with token..."
        echo ""
        read -rp "  GitHub Personal Access Token (or Enter to abort): " GH_TOKEN
        if [ -z "$GH_TOKEN" ]; then
            log_error "Cannot clone without token. Aborting."
            exit 1
        fi
        REPO_AUTH="https://${GH_TOKEN}@github.com/mdario971/cactus-flasher.git"
        git clone "$REPO_AUTH" "$APP_DIR"
        log_ok "Cloned repository with token"
    fi
fi

cd "$APP_DIR"

# ─── Step 4: Python virtual environment ──────────────────────
log_step "Step 4/8: Python virtual environment"

if [ -d "$APP_DIR/venv" ]; then
    log_info "Existing venv found, updating dependencies..."
else
    log_info "Creating virtual environment..."
    python3 -m venv "$APP_DIR/venv"
fi

bash -c "source '$APP_DIR/venv/bin/activate' && pip install --upgrade pip -q && pip install -r '$APP_DIR/requirements.txt' -q"
log_ok "Dependencies installed"

# ─── Step 5: Environment configuration ───────────────────────
log_step "Step 5/8: Environment configuration (.env)"

if [ -f "$APP_DIR/.env" ]; then
    log_ok ".env already exists (keeping current values)"
else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    sed -i "s|change-me-to-a-random-secret-at-least-32-chars|$SECRET_KEY|" "$APP_DIR/.env"
    log_ok "Generated .env with random SECRET_KEY"
fi

# ─── Step 6: Create directories & set permissions ────────────
log_step "Step 6/8: Directories & permissions"

mkdir -p "$APP_DIR/config" "$APP_DIR/uploads" "$APP_DIR/builds" "$BACKUP_DIR"

# Set ownership of everything to the app user
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chown "$APP_USER:$APP_USER" "$BACKUP_DIR"

# Permissions
chmod 755 "$APP_DIR/config" "$APP_DIR/uploads" "$APP_DIR/builds"
chmod 600 "$APP_DIR/.env"
chmod 755 "$APP_DIR/deploy.sh" 2>/dev/null || true
chmod 755 "$APP_DIR/install.sh" 2>/dev/null || true

# Lock credentials if it exists
[ -f "$APP_DIR/config/credentials.yaml" ] && chmod 600 "$APP_DIR/config/credentials.yaml"

log_ok "Permissions set — owner: $APP_USER"

# ─── Step 7: Generate & install systemd service ──────────────
log_step "Step 7/8: Systemd service"

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > "$SERVICE_FILE" << SERVICEEOF
[Unit]
Description=Cactus Flasher - ESP32 Web Flasher
After=network.target

[Service]
Type=exec
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$APP_DIR/config $APP_DIR/uploads $APP_DIR/builds
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
SERVICEEOF

log_info "Generated service file: $SERVICE_FILE"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" > /dev/null 2>&1
systemctl restart "$SERVICE_NAME"

sleep 2

if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_ok "Service is running"
else
    log_error "Service failed to start!"
    log_info "Check logs: journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi

# ─── Step 8: Write customized deploy.sh ──────────────────────
log_step "Step 8/8: Configuring deploy script"

cat > "$APP_DIR/deploy.sh" << 'DEPLOYEOF'
#!/usr/bin/env bash
# Cactus Flasher - Deploy Script
# Auto-detects paths from its own location. No hardcoded paths.
#
# Usage:
#   bash deploy.sh          # Deploy latest from main
#   bash deploy.sh v1.2.0   # Deploy specific version tag
#   bash deploy.sh rollback # Rollback to previous version

set -euo pipefail

# Auto-detect paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
APP_USER="$(stat -c '%U' "$APP_DIR")"
BACKUP_DIR="$(dirname "$APP_DIR")/cactus-flasher-backups"
SERVICE="cactus-flasher"

cd "$APP_DIR"

# Create pre-deploy backup
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
echo "==> Creating backup..."
mkdir -p "$BACKUP_DIR"
PARENT_DIR="$(dirname "$APP_DIR")"
FOLDER_NAME="$(basename "$APP_DIR")"
tar -czf "$BACKUP_DIR/pre-deploy-$TIMESTAMP.tar.gz" \
    --exclude='venv' --exclude='__pycache__' --exclude='.claude' \
    --exclude='uploads' --exclude='builds' \
    -C "$PARENT_DIR" "$FOLDER_NAME"

# Handle rollback
if [ "${1:-}" = "rollback" ]; then
    CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
    PREV_TAG=$(git tag --sort=-v:refname | sed -n '2p')
    if [ -z "$PREV_TAG" ]; then
        echo "ERROR: No previous tag to rollback to"
        exit 1
    fi
    echo "==> Rolling back from $CURRENT_TAG to $PREV_TAG"
    git checkout "$PREV_TAG"
elif [ -n "${1:-}" ]; then
    echo "==> Deploying tag: $1"
    git fetch --tags
    git checkout "$1"
else
    echo "==> Pulling latest from main..."
    git fetch origin
    git checkout main
    git pull origin main
fi

# Install/update dependencies
echo "==> Installing dependencies..."
source "$APP_DIR/venv/bin/activate"
pip install -r requirements.txt --quiet

# Restart service
echo "==> Restarting service..."
sudo systemctl restart "$SERVICE"

# Wait and check status
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
    echo "==> Deploy successful! Service is running."
    echo "    Version: $(git describe --tags --always)"
    echo "    User:    $APP_USER"
    echo "    Dir:     $APP_DIR"
else
    echo "==> ERROR: Service failed to start!"
    echo "    Check logs: sudo journalctl -u $SERVICE -n 50"
    exit 1
fi
DEPLOYEOF

chown "$APP_USER:$APP_USER" "$APP_DIR/deploy.sh"
chmod 755 "$APP_DIR/deploy.sh"
log_ok "deploy.sh configured (auto-detects paths)"

# ─── Summary ─────────────────────────────────────────────────
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  ✓ Installation complete!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}User:${NC}       $APP_USER"
echo -e "  ${BOLD}App:${NC}        $APP_DIR"
echo -e "  ${BOLD}Backups:${NC}    $BACKUP_DIR"
echo -e "  ${BOLD}Service:${NC}    systemctl status $SERVICE_NAME"
echo -e "  ${BOLD}Logs:${NC}       journalctl -u $SERVICE_NAME -f"
echo -e "  ${BOLD}Local URL:${NC}  http://127.0.0.1:8000"
echo ""
echo -e "  ${BOLD}Default login:${NC}"
echo -e "    Username: ${CYAN}admin${NC}"
echo -e "    Password: ${CYAN}cactus123${NC}"
echo -e "    ${YELLOW}⚠ Change the password immediately after first login!${NC}"
echo ""
echo -e "  ${BOLD}Deploy updates:${NC}"
echo -e "    cd $APP_DIR && bash deploy.sh"
echo ""

# ─── Optional: Nginx + SSL ───────────────────────────────────
echo -e "${BOLD}Would you like to configure Nginx reverse proxy + SSL?${NC}"
read -rp "  Enter domain (or Enter to skip): " DOMAIN

if [ -n "$DOMAIN" ]; then
    log_step "Configuring Nginx for $DOMAIN"

    cat > "/etc/nginx/sites-available/$SERVICE_NAME" << NGINXEOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINXEOF

    ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/"
    rm -f /etc/nginx/sites-enabled/default

    if nginx -t 2>/dev/null; then
        systemctl reload nginx
        log_ok "Nginx configured for $DOMAIN"

        echo ""
        read -rp "  Request SSL certificate with certbot? [Y/n]: " SSL_CONFIRM
        SSL_CONFIRM="${SSL_CONFIRM:-Y}"
        if [[ "$SSL_CONFIRM" =~ ^[Yy]$ ]]; then
            certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email || {
                log_warn "Certbot failed. Run manually later:"
                log_info "sudo certbot --nginx -d $DOMAIN"
            }
        fi
    else
        log_error "Nginx config test failed. Check: nginx -t"
    fi

    echo ""
    echo -e "  ${BOLD}Public URL:${NC} ${GREEN}https://$DOMAIN${NC}"
fi

echo ""
echo -e "${GREEN}Done! 🌵${NC}"
