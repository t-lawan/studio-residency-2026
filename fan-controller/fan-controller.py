from machine import Pin
import time

relay = Pin(26, Pin.OUT)  # change 26 to your GPIO pin

def relay_on():
    relay.value(1)
    print("Relay ON")

def relay_off():
    relay.value(0)
    print("Relay OFF")

on_time = 5   # seconds relay stays on
off_time = 5  # seconds relay stays off

while True:
    relay_on()
    time.sleep(on_time)
    relay_off()
    time.sleep(off_time)