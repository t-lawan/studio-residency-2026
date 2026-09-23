# """
# ESP32 MicroPython - AC Dimmer Test Sequence
# Slowly ramps a phase-cut AC dimmer module (RobotDyn-style, ZC + PWM/gate pins)
# from 0% to 100%, holds, ramps back down, holds.

# WIRING (typical RobotDyn-style AC Light Dimmer Module):
#   Module VCC          -> ESP32 3V3 (module logic supports 3.3V or 5V)
#   Module GND          -> ESP32 GND
#   Module ZC           -> ESP32 GPIO  (zero-cross detect input)  e.g. GPIO 4
#   Module PWM          -> ESP32 GPIO  (dim/gate trigger output)  e.g. GPIO 5
#   Module AC-IN/AC-OUT -> mains wiring to the fan (mains side, see safety notes)

# !!! DANGER: the mains-voltage side of this board is lethal. Wire everything
# fully unplugged, use an enclosure, and never touch the board/wiring while
# it is connected to mains. If unsure, get help from someone qualified. !!!

# Recommended: test with a simple incandescent bulb first (dims cleanly and
# confirms your wiring/polarity/ISR edge are correct) before trying the fan.
# """

from machine import Pin
import utime

# ---- Configuration ----
ZC_PIN = 4          # zero-cross detect input pin
GATE_PIN = 5        # PWM / trigger output pin to the module
AC_FREQ = 50         # mains frequency where you are: 50 or 60 Hz

HALF_CYCLE_US = int(1_000_000 / AC_FREQ / 2)   # 10000us @50Hz, 8333us @60Hz
PULSE_WIDTH_US = 50    # trigger pulse length sent to the module
MARGIN_US = 300         # keep delay away from the very start/end of half-cycle

MIN_DELAY_US = MARGIN_US                          # ~ max power (fires early)
MAX_DELAY_US = HALF_CYCLE_US - MARGIN_US          # ~ min power (fires late)

zc = Pin(ZC_PIN, Pin.IN, Pin.PULL_UP)
gate = Pin(GATE_PIN, Pin.OUT)
gate.value(0)

# Current firing delay in microseconds after each zero-cross.
# Updated by the main loop, read inside the ISR.
current_delay_us = MAX_DELAY_US   # start effectively "off"


def zc_handler(pin):
    # Runs once per zero crossing (twice per AC cycle).
    d = current_delay_us
    if d > 0:
        utime.sleep_us(d)
    gate.value(1)
    utime.sleep_us(PULSE_WIDTH_US)
    gate.value(0)


zc.irq(trigger=Pin.IRQ_FALLING, handler=zc_handler)
# If the fan/bulb never turns on, or behaves oddly, try Pin.IRQ_RISING
# instead -- the "active" edge of the ZC pulse can vary between board
# revisions/manufacturers.


def set_power(percent):
    """percent: 0-100"""
    global current_delay_us
    percent = max(0, min(100, percent))
    current_delay_us = int(
        MAX_DELAY_US - (percent / 100) * (MAX_DELAY_US - MIN_DELAY_US)
    )


def ramp(start, end, duration_s, step_delay_s=0.1):
    steps = max(1, int(duration_s / step_delay_s))
    for i in range(steps + 1):
        pct = start + (end - start) * i / steps
        set_power(pct)
        utime.sleep(step_delay_s)


def test_sequence():
    print("Starting at 0%")
    set_power(0)
    utime.sleep(1)

    print("Ramping 0% -> 100% over 10s")
    ramp(0, 100, 10)

    print("Holding at 100% for 10s")
    utime.sleep(10)

    print("Ramping 100% -> 0% over 10s")
    ramp(100, 0, 10)

    print("Holding at 0% for 10s")
    set_power(0)
    utime.sleep(10)

    print("Test sequence complete.")


if __name__ == "__main__":
    test_sequence()
# ESP32 MicroPython - AC Dimmer Test Sequence
# Slowly ramps a phase-cut AC dimmer module (RobotDyn-style, ZC + PWM/gate pins)
# from 0% to 100%, holds, ramps back down, holds.

# WIRING (typical RobotDyn-style AC Light Dimmer Module):
#   Module VCC          -> ESP32 3V3 (module logic supports 3.3V or 5V)
#   Module GND          -> ESP32 GND
#   Module ZC           -> ESP32 GPIO  (zero-cross detect input)  e.g. GPIO 4
#   Module PWM          -> ESP32 GPIO  (dim/gate trigger output)  e.g. GPIO 5
#   Module AC-IN/AC-OUT -> mains wiring to the fan (mains side, see safety notes)

# !!! DANGER: the mains-voltage side of this board is lethal. Wire everything
# fully unplugged, use an enclosure, and never touch the board/wiring while
# it is connected to mains. If unsure, get help from someone qualified. !!!

# Recommended: test with a simple incandescent bulb first (dims cleanly and
# confirms your wiring/polarity/ISR edge are correct) before trying the fan.

from machine import Pin
import utime

# ---- Configuration ----
ZC_PIN = 4          # zero-cross detect input pin
GATE_PIN = 5        # PWM / trigger output pin to the module
AC_FREQ = 50         # mains frequency where you are: 50 or 60 Hz

HALF_CYCLE_US = int(1_000_000 / AC_FREQ / 2)   # 10000us @50Hz, 8333us @60Hz
PULSE_WIDTH_US = 50    # trigger pulse length sent to the module
MARGIN_US = 300         # keep delay away from the very start/end of half-cycle

MIN_DELAY_US = MARGIN_US                          # ~ max power (fires early)
MAX_DELAY_US = HALF_CYCLE_US - MARGIN_US          # ~ min power (fires late)

zc = Pin(ZC_PIN, Pin.IN, Pin.PULL_UP)
gate = Pin(GATE_PIN, Pin.OUT)
gate.value(0)

# Current firing delay in microseconds after each zero-cross.
# Updated by the main loop, read inside the ISR.
current_delay_us = MAX_DELAY_US   # start effectively "off"


def zc_handler(pin):
    # Runs once per zero crossing (twice per AC cycle).
    d = current_delay_us
    if d > 0:
        utime.sleep_us(d)
    gate.value(1)
    utime.sleep_us(PULSE_WIDTH_US)
    gate.value(0)


zc.irq(trigger=Pin.IRQ_FALLING, handler=zc_handler)
# If the fan/bulb never turns on, or behaves oddly, try Pin.IRQ_RISING
# instead -- the "active" edge of the ZC pulse can vary between board
# revisions/manufacturers.


def set_power(percent):
    """percent: 0-100"""
    global current_delay_us
    percent = max(0, min(100, percent))
    current_delay_us = int(
        MAX_DELAY_US - (percent / 100) * (MAX_DELAY_US - MIN_DELAY_US)
    )


def ramp(start, end, duration_s, step_delay_s=0.1):
    steps = max(1, int(duration_s / step_delay_s))
    for i in range(steps + 1):
        pct = start + (end - start) * i / steps
        set_power(pct)
        utime.sleep(step_delay_s)


def test_sequence():
    print("Starting at 0%")
    set_power(0)
    utime.sleep(1)

    print("Ramping 0% -> 100% over 10s")
    ramp(0, 100, 10)

    print("Holding at 100% for 10s")
    utime.sleep(10)

    print("Ramping 100% -> 0% over 10s")
    ramp(100, 0, 10)

    print("Holding at 0% for 10s")
    set_power(0)
    utime.sleep(10)

    print("Test sequence complete.")


if __name__ == "__main__":
    test_sequence()