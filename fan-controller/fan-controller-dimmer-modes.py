from machine import Pin, Timer
import network
import time
import random
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

AC_FREQ_HZ = 50                     # UK mains - 50Hz
HALF_CYCLE_US = int(1_000_000 / AC_FREQ_HZ / 2)   # 10000us @50Hz

# Keep some margin off the extremes so the TRIAC reliably fires
# and so you don't try to fire right at the zero-cross edge itself.
MIN_DELAY_US = 800                  # near-full speed
MAX_DELAY_US = HALF_CYCLE_US - 800  # near-off

GATE_PULSE_US = 50                  # how long to hold the gate pin high to fire the TRIAC

# Current dim level actually being applied to the motor, 0-100.
# This is what the zero-cross handler reads every half-cycle.
dim_level = 0

# Where we're ramping toward - set by manual MQTT messages or the random mode.
target_level = 0

# --- Ramp settings (used by MODE_MANUAL and MODE_RANDOM) ---
RAMP_INTERVAL_MS = 50     # how often we nudge dim_level toward target_level
RAMP_STEP_PERCENT = 2     # how many percentage points per nudge
# e.g. 2% every 50ms = 40%/second; a full sweep 0->100 takes ~2.5s.

fire_timer = Timer(0)     # schedules the TRIAC trigger pulse after the ZC event
off_timer = Timer(1)      # turns the gate pulse back off shortly after firing
ramp_timer = Timer(2)     # periodically steps dim_level toward target_level
random_timer = Timer(3)   # schedules the next random target/hold in MODE_RANDOM

# --- Modes ---
MODE_STARTUP = "startup"   # one-shot boot sweep, drives dim_level directly
MODE_MANUAL = "manual"     # dim_level ramps toward target_level set by MQTT numbers
MODE_RANDOM = "random"     # dim_level ramps toward a randomly chosen target_level
mode = MODE_STARTUP

# --- Random mode settings ---
RANDOM_MIN_LEVEL = 15      # lowest speed the random mode will pick
RANDOM_MAX_LEVEL = 100     # highest speed the random mode will pick
RANDOM_MIN_HOLD_MS = 2000  # shortest "on/off" dwell time at a chosen speed
RANDOM_MAX_HOLD_MS = 9000  # longest dwell time at a chosen speed


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
    """Runs on every zero-cross, regardless of mode - it just reads
    whatever dim_level currently is and fires the TRIAC accordingly.
    Startup sweep, manual ramping, and random mode all just manipulate
    dim_level (directly or via the ramp timer); this handler doesn't
    need to know which mode is active."""
    if dim_level <= 0:
        gate_pin.value(0)
        return
    if dim_level >= 100:
        gate_pin.value(1)
        off_timer.init(mode=Timer.ONE_SHOT, period=1, callback=_gate_off)
        return

    delay_us = level_to_delay_us(dim_level)
    fire_timer.init(mode=Timer.ONE_SHOT, period=max(1, delay_us // 1000), callback=_fire_triac)


zc_pin.irq(trigger=Pin.IRQ_FALLING, handler=zero_cross_handler)


# --- Flow 1: startup oscillation ---
def startup_oscillation(cycles=5, low=0, high=100, step=2, step_delay_ms=30):
    """Blocking sweep: low -> high -> low, repeated `cycles` times.
    Runs before WiFi/MQTT are brought up, so the installation visibly
    'breathes' on power-up even if the network isn't available yet.
    Drives dim_level directly - no ramp timer needed since this is
    already a controlled, gradual sweep."""
    global dim_level
    print(f"Startup: oscillating {cycles} times...")
    for i in range(cycles):
        for level in range(low, high + 1, step):
            dim_level = level
            time.sleep_ms(step_delay_ms)
        for level in range(high, low - 1, -step):
            dim_level = level
            time.sleep_ms(step_delay_ms)
    dim_level = 0
    print("Startup oscillation complete")


# --- Flow 2: manual mode (driven by numeric MQTT payloads) ---
def start_manual_mode(level=None):
    global mode, target_level
    mode = MODE_MANUAL
    random_timer.deinit()  # cancel any pending random-mode step
    if level is not None:
        target_level = max(0, min(100, int(level)))
    print(f"Manual mode: target {target_level}% (ramping from {dim_level}%)")


# --- Flow 3: random oscillation mode ---
def _random_step(t):
    """Picks a new random target speed, lets the ramp timer glide dim_level
    toward it, then reschedules itself after a random hold duration.
    This is what gives the 'random on/off period' behaviour: each dwell
    period is itself randomised between RANDOM_MIN_HOLD_MS/MAX_HOLD_MS."""
    global target_level
    if mode != MODE_RANDOM:
        return  # mode was switched away before this fired - stop the chain
    target_level = random.randint(RANDOM_MIN_LEVEL, RANDOM_MAX_LEVEL)
    hold_ms = random.randint(RANDOM_MIN_HOLD_MS, RANDOM_MAX_HOLD_MS)
    print(f"Random mode: target {target_level}% for {hold_ms}ms")
    random_timer.init(mode=Timer.ONE_SHOT, period=hold_ms, callback=_random_step)


def start_random_mode():
    global mode
    mode = MODE_RANDOM
    print("Entering random oscillation mode")
    _random_step(None)  # kick off the first random target immediately


# --- Ramp timer: smoothly moves dim_level toward target_level ---
# Used by both MODE_MANUAL and MODE_RANDOM. Runs continuously in the
# background via a periodic hardware timer, independent of the MQTT
# loop, so ramping keeps happening even while wait_msg() is blocking.
def _ramp_step(t):
    global dim_level
    if mode == MODE_STARTUP:
        return  # startup_oscillation() is driving dim_level directly
    if dim_level == target_level:
        return
    if dim_level < target_level:
        dim_level = min(target_level, dim_level + RAMP_STEP_PERCENT)
    else:
        dim_level = max(target_level, dim_level - RAMP_STEP_PERCENT)


ramp_timer.init(mode=Timer.PERIODIC, period=RAMP_INTERVAL_MS, callback=_ramp_step)


# --- Wifi and MQTT setup ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("WiFi connected:", wlan.ifconfig())


def handle_message(text):
    """MQTT payload protocol:
    - a number 0-100          -> manual mode, ramp to that speed
    - the text "RANDOM"       -> switch to random oscillation mode
    - the text "STOP" / "OFF" -> manual mode, ramp down to 0
    """
    upper = text.upper()
    if upper == "RANDOM":
        start_random_mode()
        return
    if upper in ("STOP", "OFF"):
        start_manual_mode(level=0)
        return
    try:
        value = float(text)
    except ValueError:
        print("Unrecognized payload, ignoring:", text)
        return
    start_manual_mode(level=value)


def on_message(topic, msg):
    try:
        text = msg.decode().strip()
    except UnicodeDecodeError as e:
        print("Bad payload, ignoring:", msg, e)
        return

    print(f"Received '{text}' on {topic.decode()}")
    handle_message(text)


def connect_mqtt():
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
    client.set_callback(on_message)
    client.connect()
    client.subscribe(MQTT_TOPIC)
    print("MQTT connected and subscribed to", MQTT_TOPIC)
    return client


# --- Main ---
startup_oscillation()      # Flow 1: runs once, before WiFi/MQTT come up
mode = MODE_MANUAL          # default to manual mode once the sweep finishes

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