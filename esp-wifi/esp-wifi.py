import network
import time

# --- WiFi setup ---
WIFI_SSID = "THE_SUN"
WIFI_PASSWORD = "THE_SUN2046"

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    network.hostname("ESP32")
    
    if not wlan.isconnected():
        print(f"Connecting to {ssid}...")
        wlan.connect(ssid, password)
        
        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
    
    if wlan.isconnected():
        print("Connected!")
        print("IP address:", wlan.ifconfig()[0])
    else:
        print("Failed to connect.")
    
    return wlan

# Usage
connect_wifi(WIFI_SSID, WIFI_PASSWORD)