#!/usr/bin/env python3
import os, time, socket, shutil
from datetime import datetime

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
SCROLL_TICK_S = 0.05     # ~20 FPS
SCROLL_GAP_PX = 24       # gap between repeated copies
# ----------------------------

# ---------- Helpers ----------
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
    try:
        ip = os.popen("hostname -I").read().strip().split()[0]
    except Exception:
        ip = "0.0.0.0"
    return f"IP:{ip}"

def load_line():
    l1, _, _ = os.getloadavg()
    return f"CPU: {l1:.2f}"

def mem_line():
    vm = psutil.virtual_memory()
    used = vm.total - vm.available
    return f"Mem:{bytes2human(used)}/{bytes2human(vm.total)} {int(vm.percent)}%"

def disk_line():
    du = shutil.disk_usage("/")
    used = du.total - du.free
    return f"Disk: {bytes2human(used)}/{bytes2human(du.total)} {int(100*used/du.total)}%"

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

def draw_marquee_line(draw, y, state, screen_w, gap_px, speed_px):
    if not state["scroll"]:
        draw.bitmap((0, y), state["img"], fill=1)
        return
    x = state["x"]
    draw.bitmap((x, y), state["img"], fill=1)
    x2 = x + state["w"] + gap_px
    if x2 < screen_w:
        draw.bitmap((x2, y), state["img"], fill=1)
    # advance & wrap
    x -= speed_px
    total = state["w"] + gap_px
    if x < -total:
        x += total
    state["x"] = x

# ---------- Main ----------
def main():
    device = make_device()
    font_top = load_font(FONT_SIZE_TOP)
    font_bottom = load_font(FONT_SIZE_BOTTOM)

    stats = [up_line, ip_line, load_line, mem_line, disk_line]
    idx = 0
    last_rotate = time.monotonic()

    top_state = init_state()
    bottom_state = init_state()

    while True:
        now = time.monotonic()

        line1 = host_line()
        line2 = stats[idx % len(stats)]()

        ensure_state_for_text(top_state, line1, font_top, device.width)
        ensure_state_for_text(bottom_state, line2, font_bottom, device.width)

        with canvas(device) as draw:
            draw_marquee_line(draw, 0,  top_state, device.width, SCROLL_GAP_PX, SCROLL_SPEED_PX)
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
