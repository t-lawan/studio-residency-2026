from machine import Pin
from time import ticks_ms, ticks_diff, sleep

digital_pin = Pin(2, Pin.IN, Pin.PULL_UP)  # explicit pull-up in case it's needed

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
        print("No movement detected — calm")
    elif len(intervals) >= 2:
        avg_interval = sum(intervals) / len(intervals)
        freq = 1000 / avg_interval
        print("Passes/sec:", round(freq, 2))
    else:
        print("Waiting for oscillation...")

    sleep(0.2)  # check more often than before so triggers aren't missed between checks