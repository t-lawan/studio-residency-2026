import network
import mip

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.connect("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD")
while not sta.isconnected():
    pass

mip.install("umqtt.simple")