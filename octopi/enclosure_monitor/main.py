"""Module to take readings from DHT22 and report them to HA."""
from __future__ import annotations

from json import dumps
from logging import WARNING, getLogger
from os import environ
from time import sleep

from dotenv import load_dotenv
from paho.mqtt.publish import single
from pigpio import pi  # type: ignore[import-not-found]
from wg_utilities.decorators import process_exception
from wg_utilities.devices.dht22 import DHT22Sensor
from wg_utilities.loggers import add_warehouse_handler

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")

add_warehouse_handler(LOGGER, level=WARNING)

load_dotenv()

LOOP_DELAY_SECONDS = 30

DHT22_PIN = 22

MQTT_AUTH_KWARGS = {
    "hostname": environ["MQTT_HOST"],
    "auth": {
        "username": environ["MQTT_USERNAME"],
        "password": environ["MQTT_PASSWORD"],
    },
}


@process_exception(logger=LOGGER)
def main() -> int:
    """Take temp/humidity readings and upload them to HA."""

    dht22 = DHT22Sensor(pi(), DHT22_PIN)

    while True:
        dht22.trigger()
        single(
            "/homeassistant/octopi/dht22",
            payload=dumps(
                {
                    "temperature": round(dht22.temperature, 2),
                    "humidity": round(dht22.humidity, 2),
                }
            ),
            **MQTT_AUTH_KWARGS,  # type: ignore[arg-type]
        )
        sleep(LOOP_DELAY_SECONDS)


if __name__ == "__main__":
    main()
