"""
ESP32 fan node, class-based version.

Each class owns one responsibility:
  Config        -- all tunable constants in one place
  WiFiConnection -- joining the WiFi network
  Relay          -- the actual relay pin + on/off/hysteresis logic
  Oscillator    -- latest wind/oscillation reading + staleness
  HidrasNet   -- other fans' reported speeds + staleness
  Regulator     -- combines Oscillator + HidrasNet into one "drive" number
  MqttLink       -- connecting, subscribing, and routing incoming messages
  Fan        -- wires all of the above together and runs the main loop

Bugs fixed from the original while restructuring:
  - The MQTT client only subscribed to the wind topic, but on_message()
    also checked for "fan/speed/" -- that branch could never fire.
    MqttLink now subscribes to both wildcards.
  - `if fan_id == ESP_ID: neighbour_fans[fan_id] = ...` had the condition
    backwards -- it only stored a fan's OWN echoed messages, and silently
    dropped every real neighbor. HidrasNet.update() now stores anyone
    who ISN'T us, and ignores our own echo.
  - compute_drive() was fully implemented but never called; the relay
    was actually being toggled by a leftover `if value > SPEED_THRESHOLD`
    check using whatever the last message's raw value happened to be.
    Regulator.compute() is now the only thing that decides the relay.
  - `wind_oscillation_value` (set in regulator()) and `wind_value` (read
    in compute_drive()) were two different globals due to a typo -- the
    wind reading was never actually reaching the drive calculation.
    Oscillator now has a single value with no duplicate name.
"""

from machine import Pin
import network
import time
from umqtt.simple import MQTTClient
import urandom

class Config:
    ESP_ID = 1  # unique per device
    TOPIC_MY_SPEED = "fan/speed/{}".format(ESP_ID)   # topic THIS node publishes to
    

    WIFI_SSID = "THE_SUN"
    WIFI_PASSWORD = "THE_SUN2046"

    MQTT_BROKER = "192.168.0.100"
    MQTT_CLIENT_ID = "ESP32_SENSOR_{}".format(ESP_ID)

    TOPIC_WIND_WILDCARD = b"wind/oscillation/#"
    TOPIC_SPEED_WILDCARD = b"fan/speed/#"

    RELAY_PIN = 26

    SMOOTHING = 0.2

    WIND_WEIGHT = 0.1
    NEIGHBOR_WEIGHT = 0.3
    OWN_WEIGHT = 0.6

    ON_THRESHOLD = 65.0
    OFF_THRESHOLD = 30.0   # gap between ON/OFF = hysteresis, avoids relay chatter

    NEIGHBOR_TIMEOUT_MS = 5000
    WIND_TIMEOUT_MS = 5000
    MIN_DWELL_MS = 5000
    CONTROL_PERIOD_MS = 250
    PUBLISH_PERIOD_MS = 500  


class WiFiConnection:
    def __init__(self, ssid, password):
        self._ssid = ssid
        self._password = password
        self._wlan = network.WLAN(network.STA_IF)

    def connect(self):
        self._wlan.active(True)
        if not self._wlan.isconnected():
            self._wlan.connect(self._ssid, self._password)
            while not self._wlan.isconnected():
                time.sleep(0.5)
        print("WiFi connected:", self._wlan.ifconfig())


class Relay:
    def __init__(self, pin_num, min_dwell_ms=3000):
        self._pin = Pin(pin_num, Pin.OUT)
        self.is_on = False
        self._min_dwell_ms = min_dwell_ms
        self._last_change_ms = 0

    def _can_change(self, now):
        return time.ticks_diff(now, self._last_change_ms) >= self._min_dwell_ms

    def turn_on(self, now):
        if not self.is_on and self._can_change(now):
            self._pin.value(1)
            self.is_on = True
            self._last_change_ms = now
            print("Relay ON")

    def turn_off(self, now):
        if self.is_on and self._can_change(now):
            self._pin.value(0)
            self.is_on = False
            self._last_change_ms = now
            print("Relay OFF")

    def apply_threshold(self, drive, on_threshold, off_threshold, now):
        if drive >= on_threshold:
            self.turn_on(now)
        elif drive <= off_threshold:
            self.turn_off(now)


class Oscillator:
    """Latest value from the hall-sensor ESP32, with staleness handling."""

    def __init__(self, timeout_ms):
        self._timeout_ms = timeout_ms
        self.value = 0.0
        self._last_seen_ms = 0

    def update(self, value):
        self.value = value
        self._last_seen_ms = time.ticks_ms()

    def is_stale(self, now):
        return time.ticks_diff(now, self._last_seen_ms) > self._timeout_ms

    def component(self, now):
        """Value to use in the drive calculation -- 0 if stale, so a dead
        sensor doesn't silently freeze the fan at its last known reading."""
        if self.is_stale(now):
            return 0.0

        return self.value


class HidrasNet:
    """Tracks other fans' reported speeds, keyed by fan id."""

    def __init__(self, my_id, timeout_ms):
        self._my_id = my_id
        self._timeout_ms = timeout_ms
        self._fans = {}  # {fan_id: (speed, last_seen_ms)}

    def update(self, fan_id, speed):
        if fan_id == self._my_id:
            return  # this is our own message echoed back via the wildcard sub
        self._fans[fan_id] = (speed, time.ticks_ms())

    def prune_stale(self, now):
        stale = [fan_id for fan_id, (_, t) in self._fans.items()
                 if time.ticks_diff(now, t) > self._timeout_ms]
        for fan_id in stale:
            del self._fans[fan_id]

    def average_speed(self):
        if not self._fans:
            return 0.0
        return sum(speed for speed, _ in self._fans.values()) / len(self._fans)


class Regulator:
    def __init__(self, oscillator, neighbor_fans, wind_weight, neighbor_weight, own_weight):
        self._wind = oscillator
        self._neighbors = neighbor_fans
        self._wind_weight = wind_weight
        self._neighbor_weight = neighbor_weight
        self._own_weight = own_weight

    def compute(self, own_speed, now):
        self._neighbors.prune_stale(now)
        wind_component = self._wind.component(now)
        neighbor_component = self._neighbors.average_speed()
        return (self._wind_weight * wind_component
                + self._neighbor_weight * neighbor_component
                + self._own_weight * own_speed)


class MqttLink:
    """Owns the MQTT connection and routes incoming messages to whichever
    callback is interested (wind update vs. neighbor fan update)."""

    def __init__(self, client_id, broker, on_wind, on_fan_speed):
        self._client_id = client_id
        self._broker = broker
        self._on_wind = on_wind
        self._on_fan_speed = on_fan_speed
        self._client = None

    def connect(self):
        self._client = MQTTClient(self._client_id, self._broker)
        self._client.set_callback(self._dispatch)
        self._client.connect()
        self._client.subscribe(Config.TOPIC_WIND_WILDCARD)
        self._client.subscribe(Config.TOPIC_SPEED_WILDCARD)
        print("MQTT connected, subscribed to",
              Config.TOPIC_WIND_WILDCARD, Config.TOPIC_SPEED_WILDCARD)
        return self._client

    def _dispatch(self, topic, msg):
        try:
            topic = topic.decode()
            value = float(msg.decode())
        except (ValueError, UnicodeDecodeError) as e:
            print("Bad payload, ignoring:", topic, msg, e)
            return

        print("Received {} on {}".format(value, topic))

        if topic.startswith("wind/oscillation/"):
            self._on_wind(value)
            return

        if topic.startswith("fan/speed/"):
            try:
                fan_id = int(topic.split("/")[-1])
            except ValueError:
                return
            self._on_fan_speed(fan_id, value)
            return

    def check_messages(self):
        self._client.check_msg()  # non-blocking poll

    def reconnect(self):
        return self.connect()

    def publish(self, topic, value):
        self._client.publish(topic, str(value))

class SmoothedRandom:
    """Smoothly wandering value between 0-100. Each call nudges toward
    a new random target instead of jumping straight to it, so the
    output drifts naturally instead of jittering."""

    def __init__(self, smoothing=0.05):
        self._value = 0.0          # internal state, range -1..1
        self._smoothing = smoothing

    def next(self):
        target = urandom.getrandbits(16) / 32768 - 1   # random point in -1..1
        self._value += (target - self._value) * self._smoothing
        return int((self._value + 1) * 50)             # map -1..1 -> 0..100
    
class Fan:
    """Wires everything together and runs the control loop."""

    def __init__(self, config):
        self.config = config
        self.wifi = WiFiConnection(config.WIFI_SSID, config.WIFI_PASSWORD)
        self.relay = Relay(config.RELAY_PIN, config.MIN_DWELL_MS)
        self.speed_gen = SmoothedRandom(smoothing=config.SMOOTHING)
        self.oscillator = Oscillator(config.WIND_TIMEOUT_MS)
        self.neighbors = HidrasNet(config.ESP_ID, config.NEIGHBOR_TIMEOUT_MS)
        self.regulator = Regulator(
            self.oscillator, self.neighbors, config.WIND_WEIGHT, config.NEIGHBOR_WEIGHT, config.OWN_WEIGHT
        )
        self.mqtt = MqttLink(
            config.MQTT_CLIENT_ID,
            config.MQTT_BROKER,
            on_wind=self.oscillator.update,
            on_fan_speed=self.neighbors.update,
        )
        self._last_control_ms = 0
        self._last_publish_ms = 0
        self.own_speed = 0.0

    def start(self):
        self.wifi.connect()
        self.mqtt.connect()
        self._last_control_ms = time.ticks_ms()
        self._run()

    def _has_time_elapsed_since_last_control(self, now):
        return time.ticks_diff(now, self._last_control_ms) >= self.config.CONTROL_PERIOD_MS

    def _has_time_elapsed_since_last_publish(self, now):
        return time.ticks_diff(now, self._last_publish_ms) >= self.config.PUBLISH_PERIOD_MS

    def act(self, now):
        self.own_speed = self.speed_gen.next()
        drive_value = self.regulator.compute(self.own_speed, now)
        self.relay.apply_threshold(
            drive_value, self.config.ON_THRESHOLD, self.config.OFF_THRESHOLD, now
        )
        print("drive={:.1f} relay={}".format(
            drive_value, "ON" if self.relay.is_on else "OFF"
        ))

    def broadcast_my_speed(self):
        try:
            self.mqtt.publish(self.config.TOPIC_MY_SPEED, self.own_speed)
        except Exception as e:
            print("Error publishing to MQTT:", e)

    def _run(self):
        while True:
            try:
                self.mqtt.check_messages()
            except Exception as e:
                print("MQTT error, reconnecting:", e)
                try:
                    self.mqtt.reconnect()
                except Exception as e2:
                    print("Reconnect failed:", e2)
                    time.sleep(2)
                continue

            now = time.ticks_ms()
            if self._has_time_elapsed_since_last_control(now):
                self._last_control_ms = now
                self.act(now)

            if self._has_time_elapsed_since_last_publish(now):
                self._last_publish_ms = now
                self.broadcast_my_speed()

            time.sleep_ms(20)


if __name__ == "__main__":
    Fan(Config).start()
