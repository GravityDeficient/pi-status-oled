#!/usr/bin/env bash
set -euo pipefail

# OLED Monitor Setup Script
# Usage: ./install.sh [INSTALL_DIR]

# Config
SERVICE_NAME="status-oled.service"
SCRIPT_NAME="status-oled.py"
INSTALL_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"
VENV_DIR="$INSTALL_DIR/.venv"
RUN_USER="${SUDO_USER:-$USER}"

# Helpers
log() { echo -e "\033[1;32m[+] $*\033[0m"; }
warn() { echo -e "\033[1;33m[!] $*\033[0m"; }
err() { echo -e "\033[1;31m[✗] $*\033[0m"; exit 1; }

# Check prerequisites
log "Checking files..."
[[ -f "$INSTALL_DIR/$SCRIPT_NAME" ]] || err "Script not found: $INSTALL_DIR/$SCRIPT_NAME"
[[ -f "$INSTALL_DIR/requirements.txt" ]] || err "Requirements not found: $INSTALL_DIR/requirements.txt"

# Install packages and setup I2C
log "Installing system packages..."
sudo apt-get update -q
sudo apt-get install -y python3 python3-venv python3-pip i2c-tools fonts-dejavu-core

log "Enabling I2C and adding user to i2c group..."
sudo raspi-config nonint do_i2c 0 2>/dev/null || warn "Enable I2C manually with raspi-config"
sudo usermod -aG i2c "$RUN_USER"

# Setup Python environment
log "Setting up Python environment..."
rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# Create systemd service
log "Creating systemd service..."
sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true

sudo tee "/etc/systemd/system/$SERVICE_NAME" >/dev/null <<EOF
[Unit]
Description=OLED status display
After=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/$SCRIPT_NAME
SupplementaryGroups=i2c
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

# Check results
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "✓ Service started successfully!"
    if [[ -e /dev/i2c-1 ]] && command -v i2cdetect >/dev/null && i2cdetect -y 1 | grep -q "3c"; then
        log "✓ OLED display detected"
    else
        warn "OLED not detected - check wiring and reboot if needed"
    fi
else
    warn "Service failed to start. Check: journalctl -u $SERVICE_NAME"
fi

log "Setup complete! Use 'systemctl status $SERVICE_NAME' to check status"