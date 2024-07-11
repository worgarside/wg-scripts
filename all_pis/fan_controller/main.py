"""Module to take readings from DHT22 and report them to HA."""

from __future__ import annotations

from enum import IntEnum
from logging import WARNING, getLogger
from os import environ
from typing import Any, Final

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from pigpio import EITHER_EDGE  # type: ignore[import-untyped]
from pigpio import pi as rasp_pi
from wg_utilities.decorators import process_exception
from wg_utilities.functions import backoff
from wg_utilities.loggers import add_stream_handler, add_warehouse_handler

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")

add_stream_handler(LOGGER)
add_warehouse_handler(LOGGER, level=WARNING)

MQTT = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
MQTT.username_pw_set(username=environ["MQTT_USERNAME"], password=environ["MQTT_PASSWORD"])

MQTT_HOST: Final[str] = environ["MQTT_HOST"]

PI = rasp_pi()

FAN_PIN: Final[int] = int(environ["FAN_PIN"])
FAN_MQTT_TOPIC = environ["FAN_MQTT_TOPIC"]

ON_VALUES = (True, 1, "1", "on", "true", "True")
OFF_VALUES = (False, 0, "0", "off", "false", "False")


class NewPinState(IntEnum):
    """Enum for the possible states of the pin."""

    OFF = 0
    ON = 1
    WATCHDOG_TIMEOUT_NO_CHANGE = 2


@process_exception(logger=LOGGER)
def publish_state(state: bool | NewPinState) -> None:
    """Publish the state of the pin to an MQTT topic."""
    if state == NewPinState.WATCHDOG_TIMEOUT_NO_CHANGE:
        return

    MQTT.publish(FAN_MQTT_TOPIC, bool(state))

    LOGGER.info("Published state '%s' to topic '%s'", state, FAN_MQTT_TOPIC)


@MQTT.message_callback()
def on_message(_: Any, __: Any, message: mqtt.MQTTMessage) -> None:
    """Process env vars on MQTT message.

    Args:
        message (MQTTMessage): the message object from the MQTT subscription
    """
    if (value := message.payload.decode()) not in ON_VALUES + OFF_VALUES:
        raise ValueError(
            f"Invalid value received ({value}). Must be one of: "
            f"{ON_VALUES + OFF_VALUES}",
        )

    LOGGER.info("Received message: %s", value)

    pin_value = value in ON_VALUES

    LOGGER.debug("Setting pin to %s", pin_value)

    PI.write(FAN_PIN, pin_value)


@MQTT.connect_callback()
def on_connect(
    client: mqtt.Client,
    userdata: dict[str, Any],
    flags: Any,
    rc: int,
) -> None:
    """Callback for when the MQTT client connects."""
    _ = client, userdata, flags

    if rc == 0:
        LOGGER.info("Connected to MQTT broker")
    else:
        LOGGER.error("Failed to connect to MQTT broker: %s", rc)


@MQTT.disconnect_callback()
def on_disconnect(client: mqtt.Client, userdata: dict[str, Any], rc: int) -> None:
    """Callback for when the MQTT client disconnects."""
    _ = client, userdata

    if rc != 0:
        LOGGER.error("Unexpected disconnection from MQTT broker: %s", rc)
        backoff_reconnect()


@backoff(logger=LOGGER, max_delay=10, timeout=120)
def backoff_reconnect() -> None:
    """Reconnect to the MQTT broker."""
    MQTT.reconnect()


def pin_callback(gpio: int, level: NewPinState, tick: int) -> None:
    """Callback for when the pin changes state."""
    _ = gpio, tick

    if level == NewPinState.WATCHDOG_TIMEOUT_NO_CHANGE:
        return

    LOGGER.debug("Pin %s changed state to %s", gpio, level)

    publish_state(level)


@process_exception(logger=LOGGER)
def main() -> None:
    """Main function."""
    MQTT.connect(MQTT_HOST)

    MQTT.subscribe(FAN_MQTT_TOPIC)

    PI.callback(FAN_PIN, EITHER_EDGE, pin_callback)

    publish_state(PI.read(FAN_PIN))

    MQTT.loop_forever()


if __name__ == "__main__":
    main()
