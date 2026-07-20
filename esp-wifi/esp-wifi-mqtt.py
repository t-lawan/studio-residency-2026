import network
import time
import json
from umqtt.simple import MQTTClient

# --- WiFi setup ---
WIFI_SSID = "THE_SUN"
WIFI_PASSWORD = "THE_SUN2046"

# --- MQTT setup ---
MQTT_BROKER = "192.168.0.100"     # your broker's IP
MQTT_CLIENT_ID = "ESP32_test"     # unique per device if you deploy several
MQTT_TOPIC = b"esp32/status"

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    network.hostname("ESP32")

    if not wlan.isconnected():
        print(f"Connecting to {ssid}...")
        wlan.connect(ssid, password)

        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1

    if wlan.isconnected():
        print("Connected!")
        print("IP address:", wlan.ifconfig()[0])
    else:
        print("Failed to connect.")

    return wlan

def connect_mqtt():
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
    client.connect()
    print("MQTT connected")
    return client

# --- Main ---
connect_wifi(WIFI_SSID, WIFI_PASSWORD)
mqtt_client = connect_mqtt()

counter = 0
while True:
    payload = {
        "device": MQTT_CLIENT_ID,
        "counter": counter,
        "uptime": time.time()
    }
    message = json.dumps(payload)

    try:
        mqtt_client.publish(MQTT_TOPIC, message)
        print("Published:", message)
    except Exception as e:
        print("MQTT publish failed, reconnecting:", e)
        try:
            mqtt_client = connect_mqtt()
        except Exception as e2:
            print("Reconnect failed:", e2)

    counter += 1
    time.sleep(5)