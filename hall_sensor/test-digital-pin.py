from machine import Pin, ADC
from time import sleep

# Digital pin - triggers HIGH/LOW based on threshold set by the module's potentiometer
digital_pin = Pin(2, Pin.IN)

# Analog pin - raw magnetic field strength reading
# Use an ADC1 pin (32-39) - these work reliably even when WiFi is active
analog_pin = ADC(Pin(34))
analog_pin.atten(ADC.ATTN_11DB)   # full 0-3.3V range
analog_pin.width(ADC.WIDTH_12BIT) # 0-4095 resolution

while True:
    digital_value = digital_pin.value()
    analog_value = analog_pin.read()

    print("Digital:", digital_value)

    if digital_value == 0:
        print("Magnet detected!")

    sleep(0.5)