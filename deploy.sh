#!/usr/bin/env bash
# Cactus Flasher - Deploy Script
# Run on VPS: bash deploy.sh [tag|rollback]
#
# Usage:
#   bash deploy.sh          # Deploy latest from main
#   bash deploy.sh v1.2.0   # Deploy specific version tag
#   bash deploy.sh rollback # Rollback to previous version

set -euo pipefail

APP_DIR="/home/debian/cactus-flasher"
BACKUP_DIR="/home/debian/backups"
SERVICE="cactus-flasher"

cd "$APP_DIR"

# Create pre-deploy backup
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
echo "==> Creating backup..."
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/pre-deploy-$TIMESTAMP.tar.gz" \
    --exclude='venv' --exclude='__pycache__' --exclude='.claude' \
    --exclude='uploads' --exclude='builds' \
    -C /home/debian cactus-flasher

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
    # Deploy specific tag
    echo "==> Deploying tag: $1"
    git fetch --tags
    git checkout "$1"
else
    # Deploy latest from main
    echo "==> Pulling latest from main..."
    git fetch origin
    git checkout main
    git pull origin main
fi

# Install/update dependencies
echo "==> Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet

# Restart service
echo "==> Restarting service..."
sudo systemctl restart "$SERVICE"

# Wait and check status
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
    echo "==> Deploy successful! Service is running."
    echo "    Version: $(git describe --tags --always)"
else
    echo "==> ERROR: Service failed to start!"
    echo "    Check logs: sudo journalctl -u $SERVICE -n 50"
    exit 1
fi
