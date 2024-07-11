"""Module to take readings from DHT22 and report them to HA."""

from __future__ import annotations

from json import dumps
from logging import WARNING, getLogger
from os import environ
from time import sleep
from typing import Final, Literal

from paho.mqtt.publish import single
from pigpio import pi as rasp_pi  # type: ignore[import-untyped]
from wg_utilities.decorators import process_exception
from wg_utilities.devices.dht22 import DHT22Sensor
from wg_utilities.loggers import add_warehouse_handler

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")

add_warehouse_handler(LOGGER, level=WARNING)

PI = rasp_pi()

LOOP_DELAY_SECONDS = 30

DHT22_PIN: Final[Literal[6]] = 6

MQTT_HOST = environ["MQTT_HOST"]
MQTT_USERNAME = environ["MQTT_USERNAME"]
MQTT_PASSWORD = environ["MQTT_PASSWORD"]

DHT22 = DHT22Sensor(PI, DHT22_PIN)


@process_exception(logger=LOGGER)
def main() -> None:
    """Take temp/humidity readings and upload them to HA."""

    while True:
        DHT22.trigger()
        sleep(1)

        temp = round(DHT22.temperature, 2)
        rhum = round(DHT22.humidity, 2)

        if temp == DHT22.DEFAULT_TEMP_VALUE or rhum == DHT22.DEFAULT_RHUM_VALUE:
            LOGGER.warning("Bad reading from DHT22")
            sleep(LOOP_DELAY_SECONDS)
            continue

        stats = dumps(
            {
                "temperature": temp,
                "humidity": rhum,
            }
        )

        single(
            "/homeassistant/octopi/dht22",
            payload=stats,
            hostname=MQTT_HOST,
            auth={
                "username": MQTT_USERNAME,
                "password": MQTT_PASSWORD,
            },
        )

        sleep(LOOP_DELAY_SECONDS)


if __name__ == "__main__":
    main()
