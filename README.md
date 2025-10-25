# Pi Status OLED Monitor

A standalone Raspberry Pi OLED status display that shows real-time system information on a 128x32 SSD1306 I²C OLED display.

## Features

- **Real-time system monitoring**: CPU, memory, disk usage, uptime, and network info
- **Smart scrolling**: Long text scrolls smoothly with preserved positioning
- **Auto-restart**: Service automatically restarts on failure
- **Low resource usage**: Minimal CPU and memory footprint
- **Easy installation**: One-script setup with systemd service integration

## Files

- `install.sh` - Installation script for the Pi status OLED monitor
- `status-oled.py` - Python script that displays system status on OLED
- `requirements.txt` - Python dependencies

## Quick Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/GravityDeficient/pi-status-oled.git
   cd pi-status-oled
   ```

2. **Run the installation script**:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

3. **If I²C isn't enabled, reboot and run again**:
   ```bash
   sudo reboot
   # After reboot:
   cd pi-status-oled && ./install.sh
   ```

## What the Setup Does

1. **Installs system packages**: Python 3, I²C tools, fonts
2. **Enables I²C interface**: Via raspi-config (on Raspberry Pi)
3. **Adds user to i2c group**: For hardware access permissions
4. **Creates Python virtual environment**: Isolated Python environment
5. **Installs Python dependencies**: From requirements.txt
6. **Creates systemd service**: Auto-starts OLED display on boot
7. **Tests connectivity**: Scans for OLED device at I²C address 0x3C

## Hardware Requirements

- **OLED Display**: 128x32 SSD1306 I²C OLED (0x3C address)
- **Wiring**:
  - VCC → 3.3V (Pin 1)
  - GND → Ground (Pin 6)
  - SDA → GPIO 2 (Pin 3)
  - SCL → GPIO 3 (Pin 5)

## Service Management

```bash
# Check service status
systemctl status status-oled.service

# View live logs
journalctl -u status-oled.service -f

# Stop service
sudo systemctl stop status-oled.service

# Start service
sudo systemctl start status-oled.service

# Restart service
sudo systemctl restart status-oled.service

# Disable auto-start
sudo systemctl disable status-oled.service

# Enable auto-start
sudo systemctl enable status-oled.service
```

## Display Information

The OLED cycles through these system stats every 10 seconds:

- **Top line**: Hostname (always visible)
- **Bottom line** (rotates):
  - Uptime
  - IP address
  - CPU load average
  - Memory usage
  - Disk usage

## Features

- **Smart scrolling**: Long text scrolls smoothly, preserves position when numbers update
- **Auto-restart**: Service restarts on failure
- **Low resource usage**: Minimal CPU and memory footprint
- **Clean shutdown**: Graceful exit on system shutdown

## Troubleshooting

### OLED not working after setup

1. **Check I²C is enabled**:
   ```bash
   ls /dev/i2c*
   # Should show /dev/i2c-1
   ```

2. **Scan for OLED device**:
   ```bash
   i2cdetect -y 1
   # Should show '3c' at row 30, column 3c
   ```

3. **Check service logs**:
   ```bash
   journalctl -u status-oled.service -n 50
   ```

4. **Test script manually**:
   ```bash
   cd pi-status-oled
   ./.venv/bin/python status-oled.py
   ```

### Permission errors

- Make sure user is in i2c group: `groups $USER`
- If not: `sudo usermod -aG i2c $USER` then logout/login

### Python errors

- Reinstall dependencies: 
  ```bash
  cd pi-status-oled
  rm -rf .venv
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
  ```

## Customization

Edit `status-oled.py` to customize:

- `ROTATE_SECONDS`: How long each stat is displayed (default: 10)
- `SCROLL_SPEED_PX`: Scroll speed in pixels per frame (default: 4)
- `SCROLL_TICK_S`: Frame rate for scrolling (default: 0.05 = 20fps)
- `FONT_SIZE_TOP/BOTTOM`: Font sizes (default: 16)

After changes, restart the service:
```bash
sudo systemctl restart status-oled.service
```