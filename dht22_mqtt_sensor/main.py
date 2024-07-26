"""Module to take readings from DHT22 and report them to HA."""

from __future__ import annotations

from json import dumps
from logging import WARNING, getLogger
from os import environ, getenv
from socket import gethostname
from time import sleep
from typing import Final

import pigpio  # type: ignore[import-untyped]
from paho.mqtt.publish import single
from wg_utilities.decorators import process_exception
from wg_utilities.devices.dht22 import DHT22Sensor
from wg_utilities.loggers import add_warehouse_handler

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")

add_warehouse_handler(LOGGER, level=WARNING)

# =============================================================================
# Constants

PI = pigpio.pi()

LOOP_DELAY_SECONDS: Final = 30

# =============================================================================
# Environment Variables

DHT22_PIN: Final[int] = int(environ["DHT22_PIN"])

HOSTNAME = getenv("HOSTNAME", gethostname())
MQTT_USERNAME = getenv("MQTT_USERNAME", HOSTNAME)
MQTT_PASSWORD = environ["MQTT_PASSWORD"]
MQTT_HOST: Final[str] = environ["MQTT_HOST"]

MQTT_TOPIC: Final = f"/homeassistant/{HOSTNAME}/dht22"


@process_exception(logger=LOGGER)
def main() -> None:
    """Take temp/humidity readings and upload them to HA."""
    dht22 = DHT22Sensor(PI, DHT22_PIN)

    while True:
        dht22.trigger()
        sleep(1)

        temp = round(dht22.temperature, 2)
        rhum = round(dht22.humidity, 2)

        if temp == float(dht22.DEFAULT_TEMP_VALUE) or rhum == float(
            dht22.DEFAULT_RHUM_VALUE,
        ):
            LOGGER.warning("Bad reading from DHT22")
            sleep(LOOP_DELAY_SECONDS)
            continue

        single(
            MQTT_TOPIC,
            payload=dumps(
                {
                    "temperature": temp,
                    "humidity": rhum,
                },
            ),
            hostname=MQTT_HOST,
            auth={
                "username": MQTT_USERNAME,
                "password": MQTT_PASSWORD,
            },
        )

        sleep(LOOP_DELAY_SECONDS)


if __name__ == "__main__":
    main()
