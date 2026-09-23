from machine import Pin
import network
import time
from umqtt.simple import MQTTClient

# --- ESP setup ---

ESP_ID = 2  # unique name for this device

# --- WiFi setup ---
WIFI_SSID = "THE_SUN"
WIFI_PASSWORD = "THE_SUN2046"

# --- MQTT setup ---
MQTT_BROKER = "192.168.0.100"       # your broker's IP
MQTT_CLIENT_ID = f"ESP32_SENSOR_{ESP_ID}"
MQTT_OSCILLATION_TOPIC = b"wind/oscillations/1"   # topic to listen on

# --- Relay threshold control (this part is real) ---
WIND_WEIGHT = 0.4
NEIGHBOR_WEIGHT = 0.6
SPEED_THRESHOLD = 50.0

ON_THRESHOLD = 55.0
OFF_THRESHOLD = 45.0   # gap between these two = hysteresis, avoids relay chatter

NEIGHBOR_TIMEOUT_MS = 5000
WIND_TIMEOUT_MS = 5000
CONTROL_PERIOD_MS = 250


# --- Relay setup ---
relay = Pin(26, Pin.OUT)  # change 26 to your GPIO pin

# --- State ---
wind_value = 0.0
wind_last_seen = 0
neighbour_fans = {}  # {fan_id: (speed, last_seen_ms)}

def relay_on():
    update_relay_state(1)
    print("Relay ON")

def relay_off():
    update_relay_state(0)
    print("Relay OFF")

def update_relay_state(value):
    relay.value(value)

# --- Wifi and MQTT setup ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("WiFi connected:", wlan.ifconfig())

def handle_message(topic,value):
    regulator(topic, value)

def regulator(topic, value):
    global wind_oscillation_value, wind_last_seen
    now = time.ticks_ms()
    """Regulate the relay based on the received value."""
    if topic.startswith("wind/oscillation/"):
        wind_oscillation_value = value
        wind_last_seen = now
        return

    if topic.startswith("fan/speed/"):
        try:
            fan_id = int(topic.split("/")[-1])
        except ValueError:
            return
        if fan_id == ESP_ID:
            neighbour_fans[fan_id] = (value, now)
            return  # ignore our own messages
                
    if value > SPEED_THRESHOLD:
        update_relay_state(0)
    else:
        update_relay_state(1)

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


def on_message(topic, msg):
    try:
        value = float(msg.decode())
    except (ValueError, UnicodeDecodeError) as e:
        print("Bad payload, ignoring:", msg, e)
        return

    print(f"Received {value} on {topic.decode()}")

    handle_message(topic, value)


def connect_mqtt():
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
    client.set_callback(on_message)
    client.connect()
    client.subscribe(MQTT_OSCILLATION_TOPIC)
    print("MQTT connected and subscribed to", MQTT_OSCILLATION_TOPIC)
    return client

# --- Main ---
connect_wifi()
mqtt_client = connect_mqtt()

while True:
    try:
        mqtt_client.wait_msg()  # blocks until a message arrives
    except Exception as e:
        print("MQTT error, reconnecting:", e)
        try:
            mqtt_client = connect_mqtt()
        except Exception as e2:
            print("Reconnect failed:", e2)
            time.sleep(2)

