from machine import Pin
from neopixel import NeoPixel

np = NeoPixel(Pin(5), 64)  # match your GPIO
np[0] = (255, 0, 0)  # first pixel red
np.write()