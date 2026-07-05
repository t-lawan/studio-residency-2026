# Python MQTT Server for PI

Script to run MQTT Server 


## Getting Started


### Installing
Install mosquito 
```
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto
sudo systemctl start mosquitto
```


### Install MQTT 

```
 pip install paho-mqtt --break-system-packages
```

### Run script

```
 python3 main.py
```

### Test end to end

```
 mosquitto_pub -h localhost -t "installation/wind/freq" -m "3.25"
```
