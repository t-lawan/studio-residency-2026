"""
ESP32 fan node -- real relay, simulated dimmer data.

What's REAL:
  - WiFi + MQTT connection
  - subscribing to wind/oscillation/# (from the separate hall-sensor ESP32)
  - subscribing to fan/speed/# (from other fan nodes)
  - the relay switching ON/OFF, decided by a threshold (with hysteresis)
    on wind + neighbor data

What's SIMULATED:
  - the number this node publishes to fan/speed/<FAN_ID>. There's no
    dimmer, so there's no real "percentage of power" to report. Instead
    this fakes a plausible continuous value: it ramps up toward a high
    setpoint (with noise) when the relay is ON, and ramps down toward
    ~0 (with noise) when OFF -- so anything downstream (other fans, the
    video display) sees something that looks like real dimmer telemetry.
"""

from machine import Pin
import network
import time
import random
from umqtt.simple import MQTTClient

# --- ESP setup ---
FAN_ID = 2  # unique per device

# --- WiFi setup ---
WIFI_SSID = "THE_SUN"
WIFI_PASSWORD = "THE_SUN2046"

# --- MQTT setup ---
MQTT_BROKER = "192.168.0.100"
MQTT_CLIENT_ID = "ESP32_FAN_{}".format(FAN_ID)

TOPIC_MY_SPEED = "fan/speed/{}".format(FAN_ID)
TOPIC_SPEED_WILDCARD = b"fan/speed/#"
TOPIC_WIND_WILDCARD = b"wind/oscillation/#"

# --- Relay threshold control (this part is real) ---
WIND_WEIGHT = 0.7
NEIGHBOR_WEIGHT = 0.3

ON_THRESHOLD = 55.0
OFF_THRESHOLD = 45.0   # gap between these two = hysteresis, avoids relay chatter

NEIGHBOR_TIMEOUT_MS = 5000
WIND_TIMEOUT_MS = 5000
CONTROL_PERIOD_MS = 250

# --- Simulated speed broadcast (this part is fake) ---
SIM_ON_TARGET_BASE = 90.0    # fake "speed" to settle near when relay is ON
SIM_OFF_TARGET_BASE = 2.0    # fake "speed" to settle near when relay is OFF
SIM_NOISE = 4.0              # +/- random wobble each tick, for realism
SIM_SMOOTHING = 0.1          # how fast simulated value ramps toward target
PUBLISH_PERIOD_MS = 500

# --- Relay setup ---
relay = Pin(26, Pin.OUT)  # change to your GPIO pin
relay_state = False


def relay_on():
    global relay_state
    if not relay_state:
        relay.value(1)
        relay_state = True
        print("Relay ON")


def relay_off():
    global relay_state
    if relay_state:
        relay.value(0)
        relay_state = False
        print("Relay OFF")


# --- State ---
wind_value = 0.0
wind_last_seen = 0
neighbour_fans = {}  # {fan_id: (speed, last_seen_ms)}
sim_speed = 0.0  # the fake broadcast value


# --- WiFi / MQTT ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("WiFi connected:", wlan.ifconfig())


def on_message(topic, msg):
    global wind_value, wind_last_seen
    now = time.ticks_ms()
    try:
        topic = topic.decode()
        value = float(msg.decode())
    except (ValueError, UnicodeDecodeError) as e:
        print("Bad payload, ignoring:", topic, msg, e)
        return

    if topic.startswith("wind/oscillation/"):
        wind_value = value
        wind_last_seen = now
        return

    if topic.startswith("fan/speed/"):
        try:
            other_id = int(topic.split("/")[-1])
        except ValueError:
            return
        if other_id == FAN_ID:
            return  # ignore our own echoed publish
        neighbour_fans[other_id] = (value, now)
        return


def connect_mqtt():
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
    client.set_callback(on_message)
    client.connect()
    client.subscribe(TOPIC_SPEED_WILDCARD)
    client.subscribe(TOPIC_WIND_WILDCARD)
    print("MQTT connected, subscribed to", TOPIC_SPEED_WILDCARD, TOPIC_WIND_WILDCARD)
    return client


# --- Real relay control logic ---
def delete_stale_neighbour_fans(now):
    stale = [fan_id for fan_id, (_, t) in neighbour_fans.items()
             if time.ticks_diff(now, t) > NEIGHBOR_TIMEOUT_MS]
    for fan_id in stale:
        del neighbour_fans[fan_id]


def compute_drive(now):
    if time.ticks_diff(now, wind_last_seen) > WIND_TIMEOUT_MS:
        wind_component = 0.0
    else:
        wind_component = wind_value

    if neighbour_fans:
        avg_neighbor = sum(fan_speed for fan_speed, _ in neighbour_fans.values()) / len(neighbour_fans)
    else:
        avg_neighbor = 0.0

    return WIND_WEIGHT * wind_component + NEIGHBOR_WEIGHT * avg_neighbor


def apply_threshold(drive):
    if drive >= ON_THRESHOLD:
        relay_on()
    elif drive <= OFF_THRESHOLD:
        relay_off()
    # else: between thresholds -> leave relay as-is (hysteresis)


# --- Fake speed broadcast logic ---
def update_sim_speed():
    global sim_speed
    target = SIM_ON_TARGET_BASE if relay_state else SIM_OFF_TARGET_BASE
    target += random.uniform(-SIM_NOISE, SIM_NOISE)
    sim_speed += SIM_SMOOTHING * (target - sim_speed)
    sim_speed = max(0.0, min(100.0, sim_speed))


# --- Main ---
def main():
    connect_wifi()
    client = connect_mqtt()

    last_control = time.ticks_ms()
    last_publish = time.ticks_ms()

    while True:
        try:
            client.check_msg()  # non-blocking poll
        except Exception as e:
            print("MQTT error, reconnecting:", e)
            try:
                client = connect_mqtt()
            except Exception as e2:
                print("Reconnect failed:", e2)
                time.sleep(2)
            continue

        now = time.ticks_ms()

        if time.ticks_diff(now, last_control) >= CONTROL_PERIOD_MS:
            last_control = now
            delete_stale_neighbour_fans(now)
            drive = compute_drive(now)
            apply_threshold(drive)       # real relay action
            update_sim_speed()           # fake broadcast value
            print("drive={:.1f} relay={} sim_speed={:.1f}".format(
                drive, "ON" if relay_state else "OFF", sim_speed))

        if time.ticks_diff(now, last_publish) >= PUBLISH_PERIOD_MS:
            last_publish = now
            try:
                client.publish(TOPIC_MY_SPEED, "{:.1f}".format(sim_speed))
            except Exception as e:
                print("Publish failed:", e)

        time.sleep_ms(20)


main()