"""Module to take readings from DHT22 and report them to HA."""

from __future__ import annotations

from logging import INFO, WARNING, getLogger
from os import environ
from typing import TYPE_CHECKING, Any, Final, Literal

from paho.mqtt.subscribe import callback
from pigpio import pi as rasp_pi  # type: ignore[import-untyped]
from wg_utilities.decorators import process_exception
from wg_utilities.loggers import add_stream_handler, add_warehouse_handler

if TYPE_CHECKING:
    from paho.mqtt.client import MQTTMessage

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")

add_stream_handler(LOGGER, level=INFO)
add_warehouse_handler(LOGGER, level=WARNING)


PI = rasp_pi()

FAN_PIN: Final[Literal[16]] = 16
FAN_MQTT_TOPIC: Final[Literal["/prusa_i3_mk3/enclosure/fan/state"]] = (
    "/prusa_i3_mk3/enclosure/fan/state"
)

MQTT_HOST = environ["MQTT_HOST"]
MQTT_USERNAME = environ["MQTT_USERNAME"]
MQTT_PASSWORD = environ["MQTT_PASSWORD"]

ON_VALUES = (True, 1, "1", "on", "true", "True")
OFF_VALUES = (False, 0, "0", "off", "false", "False")


@process_exception(logger=LOGGER)
def on_message(_: Any, __: Any, message: MQTTMessage) -> None:
    """Process env vars on MQTT message.

    Args:
        message (MQTTMessage): the message object from the MQTT subscription
    """

    if (value := message.payload.decode()) not in ON_VALUES + OFF_VALUES:
        raise ValueError(
            f"Invalid value received ({value}). Must be one of: "
            f"{ON_VALUES + OFF_VALUES}"
        )

    pin_value = value in ON_VALUES

    LOGGER.info("Setting pin to %s", pin_value)

    PI.write(FAN_PIN, pin_value)


@process_exception(logger=LOGGER)
def setup_callback() -> None:
    """Create callback for MQTT receives.

    This is only in a function to allow decoration.
    """
    LOGGER.info("Creating callback function")
    callback(  # type: ignore[no-untyped-call]
        on_message,
        [FAN_MQTT_TOPIC],
        hostname=MQTT_HOST,
        auth={
            "username": MQTT_USERNAME,
            "password": MQTT_PASSWORD,
        },
    )
    LOGGER.info("Callback function created for topic %s", FAN_MQTT_TOPIC)


if __name__ == "__main__":
    setup_callback()
