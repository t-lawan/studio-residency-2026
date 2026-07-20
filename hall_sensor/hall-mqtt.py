from machine import Pin
from time import ticks_ms, ticks_diff, sleep
import network
from umqtt.simple import MQTTClient


# --- ESP setup ---

ESP_ID = 1  # unique name for this device

# --- WiFi setup ---
WIFI_SSID = "THE_SUN"
WIFI_PASSWORD = "THE_SUN2046"

# --- MQTT setup ---
MQTT_BROKER = "192.168.0.100"     # your broker's IP or hostname
MQTT_CLIENT_ID = f"ESP32_SENSOR_{ESP_ID}"   # unique per device if you deploy several
MQTT_TOPIC = b"wind/oscillations/1"  # topic to publish to

# --- Sensor setup ---
digital_pin = Pin(26, Pin.IN, Pin.PULL_UP)

last_trigger = ticks_ms()
intervals = []
window_size = 10
debounce_ms = 50
stale_timeout_ms = 3000

trigger_flag = False
trigger_time = 0

def magnet_detected(pin):
    global trigger_flag, trigger_time
    trigger_time = ticks_ms()
    trigger_flag = True

digital_pin.irq(trigger=Pin.IRQ_FALLING, handler=magnet_detected)

last_publish = ticks_ms()
publish_interval_ms = 1000  # send an update once per second

# --- Wifi and MQTT setup ---

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            sleep(0.5)
    print("WiFi connected:", wlan.ifconfig())

def connect_mqtt():
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
    client.connect()
    print("MQTT connected")
    return client

# --- Main ---
connect_wifi()
mqtt_client = connect_mqtt()

while True:
    if trigger_flag:
        trigger_flag = False
        diff = ticks_diff(trigger_time, last_trigger)
        if diff > debounce_ms:
            intervals.append(diff)
            if len(intervals) > window_size:
                intervals.pop(0)
            last_trigger = trigger_time

    time_since_last = ticks_diff(ticks_ms(), last_trigger)

    if time_since_last > stale_timeout_ms:
        intervals.clear()
        freq = 0.0
        status = "calm"
    elif len(intervals) >= 2:
        avg_interval = sum(intervals) / len(intervals)
        freq = 1000 / avg_interval
        status = "active"
    else:
        freq = 0.0
        status = "waiting"

    if ticks_diff(ticks_ms(), last_publish) > publish_interval_ms:
        last_publish = ticks_ms()
        payload = "{:.2f}".format(freq)
        try:
            mqtt_client.publish(MQTT_TOPIC, payload)
            print("Published:", payload, "(" + status + ")")
        except Exception as e:
            print("MQTT publish failed, reconnecting:", e)
            try:
                mqtt_client = connect_mqtt()
            except Exception as e2:
                print("Reconnect failed:", e2)

    sleep(0.2)