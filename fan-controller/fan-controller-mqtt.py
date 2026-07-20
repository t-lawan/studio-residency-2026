from machine import Pin
import network
import time
from umqtt.simple import MQTTClient

# --- ESP setup ---

ESP_ID = 1  # unique name for this device

# --- WiFi setup ---
WIFI_SSID = "THE_SUN"
WIFI_PASSWORD = "THE_SUN2046"

# --- MQTT setup ---
MQTT_BROKER = "192.168.0.100"       # your broker's IP
MQTT_CLIENT_ID = f"ESP32_SENSOR_{ESP_ID}"
MQTT_TOPIC = b"wind/oscillations/1"   # topic to listen on
THRESHOLD = 1.5

# --- Relay setup ---
relay = Pin(26, Pin.OUT)  # change 26 to your GPIO pin

def relay_on():
    relay.value(1)
    print("Relay ON")

def relay_off():
    relay.value(0)
    print("Relay OFF")

# --- Wifi and MQTT setup ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("WiFi connected:", wlan.ifconfig())

def handle_message(value):
    if value > THRESHOLD:
        relay_off()
    else:
        relay_on()

def on_message(topic, msg):
    try:
        value = float(msg.decode())
    except (ValueError, UnicodeDecodeError) as e:
        print("Bad payload, ignoring:", msg, e)
        return

    print(f"Received {value} on {topic.decode()}")

    handle_message(value)


def connect_mqtt():
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
    client.set_callback(on_message)
    client.connect()
    client.subscribe(MQTT_TOPIC)
    print("MQTT connected and subscribed to", MQTT_TOPIC)
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
