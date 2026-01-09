#!/usr/bin/env python3
import os, time, socket, shutil, re
from datetime import datetime
from subprocess import run

import psutil
from PIL import ImageFont, Image, ImageDraw
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306

# ---------- Config ----------
I2C_PORT = 1
I2C_ADDR = 0x3C
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
FONT_SIZE_TOP = 16       # hostname line
FONT_SIZE_BOTTOM = 16    # stats line
ROTATE_SECONDS = 10      # how long before switching to next stat
SCROLL_SPEED_PX = 4      # pixels per frame when scrolling
SCROLL_TICK_S = 0.1      # 10 FPS (reduced from 20 FPS)
SCROLL_GAP_PX = 24       # gap between repeated copies
CACHE_SECONDS = 2        # cache expensive operations for 2 seconds

# Anti burn-in: shift static content position periodically
BURNIN_SHIFT_SECONDS = 30   # shift position every N seconds
BURNIN_SHIFT_MAX_X = 2      # max horizontal shift in pixels
BURNIN_SHIFT_MAX_Y = 1      # max vertical shift in pixels
# ----------------------------

# Global cache for expensive operations
_cache = {
    'vcgencmd_data': {'time': 0, 'throttled': '0x0', 'temp': 'N/A'},
    'cpu_percent': {'time': 0, 'value': 0.0},
    'ip_addr': {'time': 0, 'value': '0.0.0.0'}
}

# ---------- Helpers ----------
def get_cached_vcgencmd_data():
    """Cache expensive vcgencmd calls"""
    now = time.monotonic()
    cache = _cache['vcgencmd_data']
    
    if now - cache['time'] > CACHE_SECONDS:
        try:
            # Get throttling and temperature data
            throttled_result = run(["vcgencmd", "get_throttled"], capture_output=True, text=True)
            temp_result = run(["vcgencmd", "measure_temp"], capture_output=True, text=True)
            
            cache['throttled'] = throttled_result.stdout.strip() if throttled_result.returncode == 0 else "throttled=0x0"
            cache['temp'] = temp_result.stdout.strip() if temp_result.returncode == 0 else "temp=0.0'C"
            cache['time'] = now
        except Exception:
            pass
    
    return cache

def get_cached_cpu_percent():
    """Cache CPU percentage with less frequent updates"""
    now = time.monotonic()
    cache = _cache['cpu_percent']
    
    if now - cache['time'] > 1:  # Update every 1 second instead of 2
        try:
            # Use psutil.cpu_percent() without interval for non-blocking call
            cache['value'] = psutil.cpu_percent()
            cache['time'] = now
        except Exception:
            cache['value'] = 0.0
    
    return cache['value']

def get_cached_ip():
    """Cache IP address lookup"""
    now = time.monotonic()
    cache = _cache['ip_addr']
    
    if now - cache['time'] > 10:  # Cache IP for 10 seconds
        try:
            ip = os.popen("hostname -I").read().strip().split()[0]
            cache['value'] = ip
            cache['time'] = now
        except Exception:
            pass
    
    return cache['value']

def load_font(size):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

def bytes2human(n):
    symbols = ('K', 'M', 'G', 'T')
    for i in range(len(symbols)-1, -1, -1):
        thresh = 1 << ((i + 1) * 10)
        if n >= thresh:
            return f"{int(n / thresh)}{symbols[i]}"
    return f"{n}B"

def up_line():
    uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    hours, mins = divmod(int(uptime.total_seconds() // 60), 60)
    return f"Up:{hours}h{mins}m"

def host_line():
    return socket.gethostname()

def ip_line():
    ip = get_cached_ip()
    return f"IP:{ip}"

def load_line():
    # Get cached CPU percentage and throttling status
    cpu_percent = get_cached_cpu_percent()
    
    # Get cached throttling data
    vcgencmd_data = get_cached_vcgencmd_data()
    
    try:
        throttled_hex = vcgencmd_data['throttled'].split('=')[1]
        throttled_val = int(throttled_hex, 16)
        
        # Parse throttling bits
        currently_throttled = throttled_val & 0x2  # Bit 1: Currently throttled
        temp_limit = throttled_val & 0x1           # Bit 0: Under-voltage detected
        
        # Create status indicator
        status = ""
        if currently_throttled:
            status += " THROT"  # Thermal throttling
        if temp_limit:
            status += " UV"     # Under-voltage
            
        return f"CPU: {cpu_percent:.1f}%{status}"
    except Exception:
        return f"CPU: {cpu_percent:.1f}%"

def mem_line():
    vm = psutil.virtual_memory()
    used = vm.total - vm.available
    return f"Mem:{bytes2human(used)}/{bytes2human(vm.total)} {int(vm.percent)}%"

def disk_line():
    du = shutil.disk_usage("/")
    used = du.total - du.free
    return f"Disk: {bytes2human(used)}/{bytes2human(du.total)} {int(100*used/du.total)}%"

def temp_line():
    """Get CPU temperature and detailed throttling info"""
    vcgencmd_data = get_cached_vcgencmd_data()
    
    try:
        # Parse cached temperature
        temp = "N/A"
        temp_match = re.search(r'temp=([0-9.]+)', vcgencmd_data['temp'])
        if temp_match:
            temp = f"{float(temp_match.group(1)):.1f}°C"
        
        # Parse cached throttling data
        throttle_info = ""
        throttled_hex = vcgencmd_data['throttled'].split('=')[1]
        throttled_val = int(throttled_hex, 16)
        
        # Check various throttling conditions
        if throttled_val & 0x1:    # Under-voltage detected
            throttle_info += "UV "
        if throttled_val & 0x2:    # Currently throttled
            throttle_info += "THROT "
        if throttled_val & 0x4:    # Currently capped
            throttle_info += "CAP "
        if throttled_val & 0x8:    # Currently soft temperature limit
            throttle_info += "SOFT "
            
        # Historical flags (bits 16-19)
        if throttled_val & 0x10000:  # Under-voltage has occurred
            throttle_info += "UV-H "
        if throttled_val & 0x20000:  # Throttling has occurred  
            throttle_info += "TH-H "
        
        if throttle_info:
            return f"Temp: {temp} {throttle_info.strip()}"
        else:
            return f"Temp: {temp}"
            
    except Exception:
        return "Temp: N/A"

# ---------- Anti Burn-in ----------
class BurnInShifter:
    """
    Cycles through pixel offset positions to prevent OLED burn-in.
    Creates a pattern that ensures all pixels get rest time.
    """
    def __init__(self, max_x, max_y, shift_seconds):
        self.max_x = max_x
        self.max_y = max_y
        self.shift_seconds = shift_seconds
        self.last_shift = time.monotonic()
        # Generate all offset positions in a pattern
        # Pattern: cycle through corners and center to distribute wear
        self._positions = self._generate_positions()
        self._pos_idx = 0
        self.offset_x = 0
        self.offset_y = 0

    def _generate_positions(self):
        """Generate offset positions that cycle through different areas"""
        positions = [(0, 0)]  # center/default
        # Add horizontal shifts
        for x in range(1, self.max_x + 1):
            positions.append((x, 0))
            positions.append((-x, 0))
        # Add vertical shifts
        for y in range(1, self.max_y + 1):
            positions.append((0, y))
            positions.append((0, -y))
        # Add diagonal combinations
        for x in range(1, self.max_x + 1):
            for y in range(1, self.max_y + 1):
                positions.append((x, y))
                positions.append((-x, y))
                positions.append((x, -y))
                positions.append((-x, -y))
        return positions

    def update(self):
        """Check if it's time to shift and update offset"""
        now = time.monotonic()
        if now - self.last_shift >= self.shift_seconds:
            self._pos_idx = (self._pos_idx + 1) % len(self._positions)
            self.offset_x, self.offset_y = self._positions[self._pos_idx]
            self.last_shift = now
            return True
        return False

# ---------- Display ----------
def make_device():
    serial = i2c(port=I2C_PORT, address=I2C_ADDR)
    return ssd1306(serial, width=128, height=32)

# --- marquee helpers ---
def init_state():
    return {"text": None, "img": None, "w": 0, "x": 0, "scroll": False, "text_template": None}

def render_text_image(text, font):
    # Render to exact-width 1-bit image so we can scroll precisely
    tmp = Image.new("1", (1, 1))
    d = ImageDraw.Draw(tmp)
    w = int(d.textlength(text, font=font))
    w = max(w, 1)
    # height from font metrics; fallback to 12
    try:
        h = font.getbbox("Ay")[3]
    except Exception:
        h = 12
    img = Image.new("1", (w, h), 0)
    ImageDraw.Draw(img).text((0, 0), text, font=font, fill=1)
    return img

def get_text_template(text):
    """Extract template from text by replacing numbers/percentages with placeholders"""
    import re
    # Replace sequences of digits, decimal numbers, and percentages with placeholders
    template = re.sub(r'\d+\.?\d*%?', '#', text)
    # Replace IP addresses with placeholder
    template = re.sub(r'\d+\.\d+\.\d+\.\d+', '#.#.#.#', template)
    return template

def should_preserve_scroll_position(old_text, new_text):
    """Check if scroll position should be preserved (text structure is similar)"""
    if old_text is None or new_text is None:
        return False
    return get_text_template(old_text) == get_text_template(new_text)

def ensure_state_for_text(state, text, font, screen_w):
    if text != state["text"]:
        old_text = state["text"]
        preserve_scroll = should_preserve_scroll_position(old_text, text)
        
        state["text"] = text
        state["img"] = render_text_image(text, font)
        old_w = state["w"]
        state["w"] = state["img"].width
        state["scroll"] = state["w"] > screen_w
        
        if not preserve_scroll or not state["scroll"]:
            # Reset scroll position for new text structure or non-scrolling text
            state["x"] = screen_w if state["scroll"] else 0
        else:
            # Preserve scroll position but adjust for width changes
            if old_w != state["w"]:
                # Adjust position proportionally if width changed
                if old_w > 0:
                    ratio = state["w"] / old_w
                    state["x"] = int(state["x"] * ratio)

def draw_marquee_line(draw, y, state, screen_w, gap_px, speed_px, offset_x=0, offset_y=0):
    """
    Draw a marquee line with optional pixel offset for burn-in protection.
    offset_x/offset_y shift the entire line to distribute pixel wear.
    """
    y_adj = y + offset_y
    if not state["scroll"]:
        draw.bitmap((offset_x, y_adj), state["img"], fill=1)
        return
    x = state["x"] + offset_x
    draw.bitmap((x, y_adj), state["img"], fill=1)
    x2 = x + state["w"] + gap_px
    if x2 < screen_w:
        draw.bitmap((x2, y_adj), state["img"], fill=1)
    # advance & wrap
    state["x"] -= speed_px
    total = state["w"] + gap_px
    if state["x"] < -total:
        state["x"] += total

# ---------- Main ----------
def main():
    device = make_device()
    font_top = load_font(FONT_SIZE_TOP)
    font_bottom = load_font(FONT_SIZE_BOTTOM)

    # Initialize CPU monitoring (first call always returns 0.0)
    psutil.cpu_percent()

    stats = [up_line, ip_line, load_line, mem_line, disk_line, temp_line]
    idx = 0
    last_rotate = time.monotonic()

    top_state = init_state()
    bottom_state = init_state()

    # Anti burn-in: shift static content periodically
    burnin_shifter = BurnInShifter(
        BURNIN_SHIFT_MAX_X,
        BURNIN_SHIFT_MAX_Y,
        BURNIN_SHIFT_SECONDS
    )

    while True:
        now = time.monotonic()

        # Update burn-in protection offset
        burnin_shifter.update()

        line1 = host_line()
        line2 = stats[idx % len(stats)]()

        ensure_state_for_text(top_state, line1, font_top, device.width)
        ensure_state_for_text(bottom_state, line2, font_bottom, device.width)

        with canvas(device) as draw:
            # Top line uses burn-in offset (static content protection)
            draw_marquee_line(
                draw, 0, top_state, device.width,
                SCROLL_GAP_PX, SCROLL_SPEED_PX,
                offset_x=burnin_shifter.offset_x,
                offset_y=burnin_shifter.offset_y
            )
            # Bottom line scrolls naturally, so less burn-in concern
            draw_marquee_line(draw, 16, bottom_state, device.width, SCROLL_GAP_PX, SCROLL_SPEED_PX)

        if (now - last_rotate) >= ROTATE_SECONDS:
            idx += 1
            last_rotate = now

        time.sleep(SCROLL_TICK_S)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
