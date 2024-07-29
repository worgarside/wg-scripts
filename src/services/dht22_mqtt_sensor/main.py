"""Module to take readings from DHT22 and report them to HA."""

from __future__ import annotations

from contextlib import suppress
from json import dumps
from logging import WARNING
from os import environ
from time import sleep
from typing import Final

import pigpio  # type: ignore[import-untyped]
from wg_utilities.decorators import process_exception
from wg_utilities.devices.dht22 import DHT22Sensor
from wg_utilities.loggers import add_warehouse_handler, get_streaming_logger
from wg_utilities.utils import mqtt

LOGGER = get_streaming_logger(__name__)
add_warehouse_handler(LOGGER, level=WARNING)

LOOP_DELAY_SECONDS: Final = 30

DHT22_PIN: Final[int] = int(environ["DHT22_PIN"])


@process_exception(logger=LOGGER)
def main() -> None:
    """Take temp/humidity readings and upload them to HA."""
    pi = pigpio.pi()
    dht22 = DHT22Sensor(pi, DHT22_PIN)

    mqtt.CLIENT.connect(mqtt.MQTT_HOST)

    with suppress(KeyboardInterrupt):
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

            payload = dumps({"temperature": temp, "humidity": rhum})

            mqtt.CLIENT.publish(
                f"/homeassistant/{mqtt.HOSTNAME}/dht22",
                payload=payload,
                qos=1,
                retain=False,
            ).wait_for_publish(timeout=5)

            LOGGER.debug("Published DHT22 reading: %s", payload)

            sleep(LOOP_DELAY_SECONDS)

    LOGGER.info("Shutting down DHT22 sensor")
    mqtt.CLIENT.disconnect()
    pi.stop()


if __name__ == "__main__":
    main()
