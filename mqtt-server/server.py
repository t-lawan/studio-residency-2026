import paho.mqtt.client as mqtt

BROKER_HOST = "localhost"  # running on the same Pi as the broker
BROKER_PORT = 1883

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Connected to broker")
        client.subscribe("#")  # "#" = subscribe to every topic
    else:
        print("Connection failed, code:", rc)

def on_message(client, userdata, msg):
    print(f"[{msg.topic}] {msg.payload.decode()}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
client.loop_forever()