import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from datetime import datetime
import json

BROKER_HOST = "localhost"
BROKER_PORT = 1883

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to broker")
        print(f"Flags: {flags}")
        if properties is not None:
            print(f"Properties: {properties.json()}")
        client.subscribe("#")
    else:
        print("Connection failed, reason code:", reason_code)

def on_message(client, userdata, msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    try:
        payload = msg.payload.decode()
    except UnicodeDecodeError:
        payload = f"<binary, {len(msg.payload)} bytes>"

    client_id = client._client_id.decode() if client._client_id else "unknown"

    print(f"[{timestamp}] client_id={client_id} userdata={userdata} | {msg.topic} => {payload}")

client = mqtt.Client(CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
client.loop_forever()