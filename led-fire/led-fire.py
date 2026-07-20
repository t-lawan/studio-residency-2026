from machine import Pin
from neopixel import NeoPixel
import time
import math
import random

# --- Matrix setup ---
NUM_PIXELS = 64
MATRIX_PIN = 5  # change to whatever GPIO you wired DIN to
np = NeoPixel(Pin(MATRIX_PIN), NUM_PIXELS)

WIDTH = 8
HEIGHT = 8

# --- Sun colors (warm core -> outer glow) ---
CORE_COLOR = (255, 200, 50)     # bright warm yellow
MID_COLOR = (255, 140, 20)      # orange
EDGE_COLOR = (200, 60, 10)      # deep red-orange

def xy_to_index(x, y):
    # Adjust this if your panel wiring is serpentine (zig-zag rows)
    if y % 2 == 0:
        return y * WIDTH + x
    else:
        return y * WIDTH + (WIDTH - 1 - x)

def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

def scale_color(c, factor):
    return tuple(min(255, max(0, int(ch * factor))) for ch in c)

def distance_from_center(x, y):
    cx, cy = (WIDTH - 1) / 2, (HEIGHT - 1) / 2
    return math.sqrt((x - cx) ** 2 + (y - cy) ** 2)

max_dist = distance_from_center(0, 0)

def render_sun(brightness=1.0, flicker=0.0):
    for y in range(HEIGHT):
        for x in range(WIDTH):
            dist = distance_from_center(x, y)
            t = dist / max_dist  # 0 = center, 1 = corner

            if t < 0.4:
                color = lerp_color(CORE_COLOR, MID_COLOR, t / 0.4)
            else:
                color = lerp_color(MID_COLOR, EDGE_COLOR, (t - 0.4) / 0.6)

            # apply breathing brightness + tiny random flicker per pixel
            local_flicker = 1.0 + random.uniform(-flicker, flicker)
            final = scale_color(color, brightness * local_flicker)

            np[xy_to_index(x, y)] = final
    np.write()

def sun_animation():
    t = 0
    while True:
        # slow breathing pulse using a sine wave, ranges ~0.6 to 1.0
        breathing = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t))
        render_sun(brightness=breathing, flicker=0.06)
        t += 0.05
        time.sleep(0.05)

sun_animation()