from machine import Pin, Timer
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
MQTT_TOPIC = b"wind/oscillations/1"   # topic to listen on

# --- Dimmer setup ---
# AC dimmer modules (e.g. RobotDyn-style) expose two lines:
#   ZC_PIN  - zero-cross detection output from the module -> ESP32 input (interrupt)
#   GATE_PIN - trigger input on the module -> ESP32 output (fires the TRIAC)
ZC_PIN_NUM = 27     # change to whatever pin you wire the module's ZC output to
GATE_PIN_NUM = 26   # change to whatever pin you wire the module's dim/gate input to

zc_pin = Pin(ZC_PIN_NUM, Pin.IN, Pin.PULL_UP)
gate_pin = Pin(GATE_PIN_NUM, Pin.OUT)
gate_pin.value(0)

AC_FREQ_HZ = 50                     # set to 60 if you're on 60Hz mains
HALF_CYCLE_US = int(1_000_000 / AC_FREQ_HZ / 2)   # 10000us @50Hz, 8333us @60Hz

# Keep some margin off the extremes so the TRIAC reliably fires
# and so you don't try to fire right at the zero-cross edge itself.
MIN_DELAY_US = 800                  # near-full brightness/speed
MAX_DELAY_US = HALF_CYCLE_US - 800  # near-off

GATE_PULSE_US = 50                  # how long to hold the gate pin high to fire the TRIAC

# Current dim level actually being applied to the motor, 0-100.
# This is what the zero-cross handler reads every half-cycle.
dim_level = 0

# Where we're ramping toward - set by incoming MQTT messages.
target_level = 0

# --- Ramp settings ---
RAMP_INTERVAL_MS = 50     # how often we nudge dim_level toward target_level
RAMP_STEP_PERCENT = 2     # how many percentage points per nudge
# e.g. 2% every 50ms = 40%/second full sweep 0->100 takes ~2.5s.
# Smaller step / longer interval = slower, gentler ramp.

fire_timer = Timer(0)   # schedules the TRIAC trigger pulse after the ZC event
off_timer = Timer(1)    # turns the gate pulse back off shortly after firing
ramp_timer = Timer(2)   # periodically steps dim_level toward target_level


def level_to_delay_us(level):
    """Map 0-100 dim level to a firing delay within the AC half-cycle.
    100 -> MIN_DELAY_US (fires almost immediately -> full power)
    0   -> MAX_DELAY_US (fires almost at the next zero-cross -> off)
    """
    level = max(0, min(100, level))
    span = MAX_DELAY_US - MIN_DELAY_US
    return int(MAX_DELAY_US - (level / 100) * span)


def _gate_off(t):
    gate_pin.value(0)


def _fire_triac(t):
    gate_pin.value(1)
    off_timer.init(mode=Timer.ONE_SHOT, period=1, callback=_gate_off)
    # period=1ms is the smallest Timer granularity on most ports; if you need
    # a tighter pulse width use utime.sleep_us(GATE_PULSE_US) here instead
    # (fine since this callback body is short), e.g.:
    # gate_pin.value(1)
    # time.sleep_us(GATE_PULSE_US)
    # gate_pin.value(0)


def zero_cross_handler(pin):
    if dim_level <= 0:
        gate_pin.value(0)
        return
    if dim_level >= 100:
        # Effectively full on: fire immediately
        gate_pin.value(1)
        off_timer.init(mode=Timer.ONE_SHOT, period=1, callback=_gate_off)
        return

    delay_us = level_to_delay_us(dim_level)
    fire_timer.init(mode=Timer.ONE_SHOT, period=max(1, delay_us // 1000), callback=_fire_triac)
    # Timer here works in ms; for microsecond-accurate firing on ESP32 you can
    # instead use machine.Timer with period in us if your port supports it,
    # or busy-wait with time.sleep_us(delay_us) inside a lightweight
    # secondary thread/core if precision matters more than simplicity.


zc_pin.irq(trigger=Pin.IRQ_FALLING, handler=zero_cross_handler)


def _ramp_step(t):
    """Nudges dim_level toward target_level by RAMP_STEP_PERCENT.
    Runs on a periodic hardware timer, independent of the MQTT loop,
    so the motor keeps ramping smoothly even while wait_msg() is blocking."""
    global dim_level
    if dim_level == target_level:
        return
    if dim_level < target_level:
        dim_level = min(target_level, dim_level + RAMP_STEP_PERCENT)
    else:
        dim_level = max(target_level, dim_level - RAMP_STEP_PERCENT)


ramp_timer.init(mode=Timer.PERIODIC, period=RAMP_INTERVAL_MS, callback=_ramp_step)


def set_speed(level):
    """Set the target dimmer/motor speed as a percentage 0-100.
    dim_level will ramp toward this smoothly rather than jumping instantly."""
    global target_level
    target_level = max(0, min(100, int(level)))
    print(f"Target speed set to {target_level}% (ramping from {dim_level}%)")


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
    # value is expected to be an integer/float 0-100 representing desired
    # dimmer/motor speed percentage, coming straight from the MQTT payload.
    set_speed(value)


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