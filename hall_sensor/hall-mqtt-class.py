from machine import Pin
from time import ticks_ms, ticks_diff, sleep
import network
from umqtt.simple import MQTTClient


class WiFiManager:
    def __init__(self, ssid, password):
        self.ssid = ssid
        self.password = password
        self.wlan = network.WLAN(network.STA_IF)

    def connect(self):
        self.wlan.active(True)
        if not self.wlan.isconnected():
            self.wlan.connect(self.ssid, self.password)
            while not self.wlan.isconnected():
                sleep(0.5)
        print("WiFi connected:", self.wlan.ifconfig())

    def is_connected(self):
        return self.wlan.isconnected()


class MQTTManager:
    def __init__(self, client_id, broker, topic):
        self.client_id = client_id
        self.broker = broker
        self.topic = topic
        self.client = None

    def connect(self):
        self.client = MQTTClient(self.client_id, self.broker)
        self.client.connect()
        print("MQTT connected")
        return self.client

    def publish(self, payload):
        try:
            self.client.publish(self.topic, payload)
            return True
        except Exception as e:
            print("MQTT publish failed, reconnecting:", e)
            try:
                self.connect()
            except Exception as e2:
                print("Reconnect failed:", e2)
            return False


class OscillationSensor:
    """Tracks magnet-trigger intervals on a digital pin to estimate frequency."""

    def __init__(self, pin_num, window_size=10, debounce_ms=50, stale_timeout_ms=3000):
        self.window_size = window_size
        self.debounce_ms = debounce_ms
        self.stale_timeout_ms = stale_timeout_ms

        self.pin = Pin(pin_num, Pin.IN, Pin.PULL_UP)
        self.last_trigger = ticks_ms()
        self.intervals = []

        self._trigger_flag = False
        self._trigger_time = 0

        self.pin.irq(trigger=Pin.IRQ_FALLING, handler=self._on_trigger)

    def _on_trigger(self, pin):
        # Keep IRQ handler minimal: just stash the timestamp and flag it.
        self._trigger_time = ticks_ms()
        self._trigger_flag = True

    def _process_pending_trigger(self):
        if not self._trigger_flag:
            return
        self._trigger_flag = False

        diff = ticks_diff(self._trigger_time, self.last_trigger)
        if diff > self.debounce_ms:
            self.intervals.append(diff)
            if len(self.intervals) > self.window_size:
                self.intervals.pop(0)
            self.last_trigger = self._trigger_time

    def update(self):
        """Process any pending trigger and return (freq_hz, status)."""
        self._process_pending_trigger()

        time_since_last = ticks_diff(ticks_ms(), self.last_trigger)

        if time_since_last > self.stale_timeout_ms:
            self.intervals.clear()
            return 0.0, "calm"

        if len(self.intervals) >= 2:
            avg_interval = sum(self.intervals) / len(self.intervals)
            freq = 1000 / avg_interval
            return freq, "active"

        return 0.0, "waiting"


class WindOscillationMonitor:
    """Ties sensor, WiFi, and MQTT together and runs the main loop."""

    def __init__(self, esp_id, wifi_ssid, wifi_password, mqtt_broker,
                 sensor_pin=26, publish_interval_ms=1000):
        self.publish_interval_ms = publish_interval_ms

        self.wifi = WiFiManager(wifi_ssid, wifi_password)
        self.mqtt = MQTTManager(
            client_id=f"ESP32_SENSOR_{esp_id}",
            broker=mqtt_broker,
            topic=f"wind/oscillations/{esp_id}".encode(),
        )
        self.sensor = OscillationSensor(sensor_pin)

        self.last_publish = ticks_ms()

    def start(self):
        self.wifi.connect()
        self.mqtt.connect()

    def run_forever(self):
        while True:
            freq, status = self.sensor.update()

            if ticks_diff(ticks_ms(), self.last_publish) > self.publish_interval_ms:
                self.last_publish = ticks_ms()
                payload = "{:.2f}".format(freq)
                if self.mqtt.publish(payload):
                    print("Published:", payload, "(" + status + ")")

            sleep(0.2)


if __name__ == "__main__":
    monitor = WindOscillationMonitor(
        esp_id=1,
        wifi_ssid="THE_SUN",
        wifi_password="THE_SUN2046",
        mqtt_broker="192.168.0.100",
        sensor_pin=26,
        publish_interval_ms=1000,
    )
    monitor.start()
    monitor.run_forever()