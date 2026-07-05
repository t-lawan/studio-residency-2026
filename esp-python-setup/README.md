# Python setup for ESP32

Repository for all CODE related to residency


## Getting Started

```
 cd esp-python-setup
```

### Installing

```
 pip install esptool
```


### Erase ESP

```
 python -m esptool --port COM5 erase-flash
```

### Setup ESP for MicroPython

```
 python -m esptool --port COM5 --baud 460800 write_flash 0x1000 .\ESP32_GENERIC-20260406-v1.28.0.bin
```