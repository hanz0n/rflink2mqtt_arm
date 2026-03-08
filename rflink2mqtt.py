#!/usr/bin/python3

import serial
import paho.mqtt.client as mqtt
import os
import logging
import json

# -----------------------------
# Logging
# -----------------------------

formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("rflink2mqtt")
logger.setLevel(logging.DEBUG)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)

# -----------------------------
# Environment variables
# -----------------------------

USB_INTERFACE = os.environ.get("USB_INTERFACE", "/dev/ttyUSB0")
MQTT_SERVER = os.environ.get("MQTT_SERVER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PWD = os.environ.get("MQTT_PWD")

DELIM = ";"

# -----------------------------
# Lookups
# -----------------------------

HSTATUS_LOOKUP = {
    "0": "normal",
    "1": "comfortable",
    "2": "dry",
    "3": "wet",
}

BFORECAST_LOOKUP = {
    "0": "no_info",
    "1": "sunny",
    "2": "partly_cloudy",
    "3": "cloudy",
    "4": "rain",
}

# -----------------------------
# Value translation
# -----------------------------

def signed_to_float(hex_value):
    value = int(hex_value, 16)
    if value & 0x8000:
        return -(value & 0x7FFF) / 10.0
    return value / 10.0


VALUE_TRANSLATION = {
    "temp": signed_to_float,
    "hum": int,
    "baro": lambda x: int(x, 16),
    "rain": lambda x: int(x, 16) / 10,
    "rainrate": lambda x: int(x, 16) / 10,
    "raintot": lambda x: int(x, 16) / 10,
    "winsp": lambda x: int(x, 16) / 10,
    "awinsp": lambda x: int(x, 16) / 10,
    "wings": lambda x: int(x, 16) / 10,
    "windir": lambda x: int(x) * 22.5,
    "uv": lambda x: int(x, 16),
    "lux": lambda x: int(x, 16),
    "kwatt": lambda x: int(x, 16),
    "watt": lambda x: int(x, 16),
}

PACKET_FIELDS = {
    "temp": "temperature",
    "hum": "humidity",
    "baro": "barometric_pressure",
    "rain": "total_rain",
    "rainrate": "rain_rate",
    "raintot": "total_rain",
    "winsp": "windspeed",
    "awinsp": "average_windspeed",
    "wings": "windgust",
    "windir": "winddirection",
    "uv": "uv",
    "lux": "lux",
    "kwatt": "kilowatt",
    "watt": "watt",
}

# -----------------------------
# MQTT
# -----------------------------

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

if MQTT_USERNAME and MQTT_PWD:
    client.username_pw_set(MQTT_USERNAME, MQTT_PWD)

discovered = set()

# -----------------------------
# Home Assistant discovery
# -----------------------------

def publish_discovery(device_id, name):

    uid = f"rflink_{device_id}_{name}"

    if uid in discovered:
        return

    topic = f"homeassistant/sensor/rflink/{uid}/config"

    payload = {
        "name": f"RFLink {device_id} {name}",
        "state_topic": f"rflink/{device_id}/{name}",
        "unique_id": uid,
        "device": {
            "identifiers": [f"rflink_{device_id}"],
            "name": f"RFLink {device_id}",
            "manufacturer": "RFLink"
        }
    }

    client.publish(topic, json.dumps(payload), retain=True)

    discovered.add(uid)

    logger.info(f"Discovery published: {topic}")

# -----------------------------
# MQTT callbacks
# -----------------------------

def on_connect(client, userdata, flags, reason_code, properties):

    if reason_code == 0:
        logger.info(f"Connected to MQTT {MQTT_SERVER}")
        client.subscribe("rflink2/tx")
    else:
        logger.error(f"MQTT connection failed: {reason_code}")


def on_message(client, userdata, message):

    payload = message.payload.decode("utf-8")

    logger.info(f"Send to RFLink: {payload}")

    ser.write((payload + "\r\n").encode())


client.on_connect = on_connect
client.on_message = on_message

# -----------------------------
# Serial
# -----------------------------

try:

    ser = serial.Serial(
        port=USB_INTERFACE,
        baudrate=57600,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=None
    )

    ser.flushInput()
    ser.flushOutput()

    logger.info(f"Connected to serial device {USB_INTERFACE}")

except Exception as e:

    logger.error(f"Could not open serial device {USB_INTERFACE}")
    raise e

# -----------------------------
# Packet decoding
# -----------------------------

def decode_packet(packet):

    try:
        node_id, _, protocol, attrs = packet.split(DELIM, 3)
    except ValueError:
        logger.debug(f"Ignored line: {packet}")
        return

    logger.info(f"Protocol: {protocol}")

    device_id = None
    switch = None

    for attr in filter(None, attrs.strip(DELIM).split(DELIM)):

        if "=" not in attr:
            continue

        key, value = attr.lower().split("=")

        if key == "id":
            device_id = value
            continue

        if key == "switch":
            switch = value
            continue

        if key in VALUE_TRANSLATION:
            value = VALUE_TRANSLATION[key](value)

        name = PACKET_FIELDS.get(key, key)

        if not device_id:
            continue

        if switch:
            topic = f"rflink/{device_id}/{name}/{switch}"
        else:
            topic = f"rflink/{device_id}/{name}"

        publish_discovery(device_id, name)

        client.publish(topic, value)

        logger.info(f"{topic} -> {value}")

# -----------------------------
# Start MQTT
# -----------------------------

client.connect(MQTT_SERVER, MQTT_PORT)
client.loop_start()

# -----------------------------
# Main loop
# -----------------------------

logger.info("RFLink -> MQTT bridge started")

while True:

    try:

        line = ser.readline()

        if not line:
            continue

        line = line.decode("utf-8").strip()

        logger.debug(f"RX: {line}")

        decode_packet(line)

    except Exception as e:

        logger.error(f"Error processing packet: {e}")
