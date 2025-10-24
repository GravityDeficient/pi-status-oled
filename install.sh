#!/usr/bin/env bash
set -euo pipefail

# ===== OLED Monitor Setup Script =====
# This script installs and configures the OLED status monitor
# as a standalone component.

# ===== Config =====
SERVICE_NAME="status-oled.service"
PYTHON_BIN="python3"
OLED_REL_DIR="."              # relative path to OLED script
OLED_SCRIPT="status-oled.py"           # OLED script filename
I2C_GROUP="i2c"

# Repo location
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# ==================

# ---------- helpers ----------
log()  { echo -e "\033[1;32m[+] $*\033[0m"; }
warn() { echo -e "\033[1;33m[!] $*\033[0m"; }
err()  { echo -e "\033[1;31m[✗] $*\033[0m"; exit 1; }

RUN_USER="${SUDO_USER:-$USER}"
[[ -n "$RUN_USER" ]] || err "Could not determine invoking user"

# ---------- prerequisites check ----------
log "Checking prerequisites..."
[[ -d "$REPO_DIR" ]] || err "Repository not found at $REPO_DIR"

OLED_DIR="$REPO_DIR/$OLED_REL_DIR"
[[ -d "$OLED_DIR" ]] || err "OLED directory not found: $OLED_DIR"
[[ -f "$OLED_DIR/$OLED_SCRIPT" ]] || err "OLED script not found: $OLED_DIR/$OLED_SCRIPT"
[[ -f "$OLED_DIR/requirements.txt" ]] || err "Requirements file not found: $OLED_DIR/requirements.txt"

# ---------- system packages ----------
log "Installing required system packages..."
sudo apt-get update -y
sudo apt-get install -y \
  ${PYTHON_BIN} \
  ${PYTHON_BIN}-venv \
  python3-pip \
  i2c-tools \
  fonts-dejavu-core

# ---------- enable I²C ----------
log "Enabling I²C interface..."
if command -v raspi-config >/dev/null 2>&1; then
  sudo raspi-config nonint do_i2c 0 || true
  log "I²C enabled via raspi-config"
else
  warn "raspi-config not found. Please enable I²C manually:"
  warn "  1. Run 'sudo raspi-config'"
  warn "  2. Go to 'Interface Options' > 'I2C' > 'Yes'"
  warn "  3. Reboot when prompted"
fi

# ---------- user groups ----------
log "Adding user ${RUN_USER} to ${I2C_GROUP} group..."
sudo usermod -aG "${I2C_GROUP}" "$RUN_USER" || true

# ---------- Python virtual environment ----------
VENV_DIR="$OLED_DIR/.venv"
log "Setting up Python virtual environment..."

if [[ -d "$VENV_DIR" ]]; then
  log "Virtual environment already exists, removing old one..."
  rm -rf "$VENV_DIR"
fi

log "Creating new virtual environment..."
${PYTHON_BIN} -m venv "$VENV_DIR"

log "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$OLED_DIR/requirements.txt"

# ---------- systemd service ----------
UNIT_PATH="/etc/systemd/system/$SERVICE_NAME"
log "Installing systemd service: $SERVICE_NAME"

# Stop existing service if running
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
  log "Stopping existing $SERVICE_NAME..."
  sudo systemctl stop "$SERVICE_NAME"
fi

sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=OLED status display
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${OLED_DIR}
ExecStart=${VENV_DIR}/bin/python ${OLED_DIR}/${OLED_SCRIPT}
SupplementaryGroups=${I2C_GROUP}
KillSignal=SIGINT
TimeoutStopSec=5s
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

# ---------- test I²C connectivity ----------
log "Testing I²C connectivity..."
if [[ -e /dev/i2c-1 ]]; then
  log "I²C device /dev/i2c-1 found"
  if command -v i2cdetect >/dev/null 2>&1; then
    log "Scanning for I²C devices..."
    if i2cdetect -y 1 | grep -q "3c"; then
      log "✓ OLED display detected at address 0x3C"
    else
      warn "No device found at 0x3C. Please check OLED wiring:"
      warn "  VCC -> 3.3V"
      warn "  GND -> Ground"
      warn "  SDA -> GPIO 2 (Pin 3)"
      warn "  SCL -> GPIO 3 (Pin 5)"
    fi
  fi
else
  warn "I²C device /dev/i2c-1 not found. Reboot may be required."
fi

# ---------- start service ----------
log "Starting OLED service..."
sudo systemctl start "$SERVICE_NAME"

# Give it a moment to start
sleep 2

# Check service status
if systemctl is-active --quiet "$SERVICE_NAME"; then
  log "✓ OLED service is running successfully!"
else
  warn "Service failed to start. Check logs with: journalctl -u $SERVICE_NAME"
fi

# ---------- finish ----------
log ""
log "=== OLED Monitor Setup Complete ==="
log ""
log "Service name: $SERVICE_NAME"
log "Service status: systemctl status $SERVICE_NAME"
log "Service logs: journalctl -u $SERVICE_NAME -f"
log "Stop service: sudo systemctl stop $SERVICE_NAME"
log "Start service: sudo systemctl start $SERVICE_NAME"
log "Restart service: sudo systemctl restart $SERVICE_NAME"
log ""

if [[ ! -e /dev/i2c-1 ]]; then
  warn "IMPORTANT: I²C device not detected. Please reboot and run again:"
  warn "  sudo reboot"
  warn "  cd $REPO_DIR && ./setup-oled.sh"
else
  log "Setup complete! The OLED display should now be showing system status."
fi