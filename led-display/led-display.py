"""
Stellar Unicorn - 4-quadrant MQTT "fan alive" indicator.

Subscribes to fan/1, fan/2, fan/3, fan/4. Each of the 4 quadrants of the
16x16 display shows a solid colour if a message has been received on the
matching topic within the last TIMEOUT_MS, otherwise it goes black.

Requires umqtt.simple to be present on the device (copy umqtt/simple.py
onto the Pico, or run `import mip; mip.install("umqtt.simple")` once
connected to wifi from the REPL).
"""

import time
import network
from stellar_unicorn import StellarUnicorn
from picographics import PicoGraphics, DISPLAY_STELLAR_UNICORN
from umqtt.simple import MQTTClient

# ---------------- CONFIG ----------------
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

MQTT_BROKER = "192.168.1.100"   # your broker IP/hostname
MQTT_PORT = 1883
MQTT_CLIENT_ID = "stellar-unicorn-fans"
MQTT_USER = None                # set if your broker needs auth
MQTT_PASSWORD = None

TIMEOUT_MS = 2 * 60 * 1000      # 2 minutes

TOPICS = [b"fan/1", b"fan/2", b"fan/3", b"fan/4"]

# colour shown for each fan while "alive" (R, G, B)
COLORS = [
    (255, 0, 0),      # fan/1 - red
    (0, 255, 0),      # fan/2 - green
    (0, 100, 255),    # fan/3 - blue
    (255, 200, 0),    # fan/4 - yellow
]

BRIGHTNESS = 0.5
# -----------------------------------------

su = StellarUnicorn()
graphics = PicoGraphics(DISPLAY_STELLAR_UNICORN)

WIDTH, HEIGHT = 16, 16
HALF_W, HALF_H = WIDTH // 2, HEIGHT // 2

QUADRANT_OFFSETS = [
    (0, 0),             # fan/1 - top-left
    (HALF_W, 0),         # fan/2 - top-right
    (0, HALF_H),         # fan/3 - bottom-left
    (HALF_W, HALF_H),    # fan/4 - bottom-right
]

# 0 means "never seen"
last_seen = [0, 0, 0, 0]

BLACK = graphics.create_pen(0, 0, 0)
PENS = [graphics.create_pen(*c) for c in COLORS]


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    print("Connecting to wifi...")
    while not wlan.isconnected():
        time.sleep(0.5)
    print("Wifi connected:", wlan.ifconfig())


def mqtt_callback(topic, msg):
    for i, t in enumerate(TOPICS):
        if topic == t:
            last_seen[i] = time.ticks_ms()
            print("Heartbeat on", t.decode())
            break


def connect_mqtt():
    client = MQTTClient(
        MQTT_CLIENT_ID,
        MQTT_BROKER,
        port=MQTT_PORT,
        user=MQTT_USER,
        password=MQTT_PASSWORD,
        keepalive=60,
    )
    client.set_callback(mqtt_callback)
    client.connect()
    for t in TOPICS:
        client.subscribe(t)
    print("MQTT connected, subscribed to", [t.decode() for t in TOPICS])
    return client


def draw_quadrants():
    graphics.set_pen(BLACK)
    graphics.clear()

    now = time.ticks_ms()
    for i in range(4):
        alive = last_seen[i] != 0 and time.ticks_diff(now, last_seen[i]) < TIMEOUT_MS
        graphics.set_pen(PENS[i] if alive else BLACK)
        x_off, y_off = QUADRANT_OFFSETS[i]
        graphics.rectangle(x_off, y_off, HALF_W, HALF_H)

    su.update(graphics)


def main():
    su.set_brightness(BRIGHTNESS)
    connect_wifi()
    client = connect_mqtt()

    while True:
        try:
            client.check_msg()
        except OSError as e:
            print("MQTT error, reconnecting...", e)
            try:
                client.disconnect()
            except Exception:
                pass
            time.sleep(2)
            try:
                client = connect_mqtt()
            except Exception as e2:
                print("Reconnect failed:", e2)
                time.sleep(5)
                continue

        draw_quadrants()
        time.sleep(0.2)


main()