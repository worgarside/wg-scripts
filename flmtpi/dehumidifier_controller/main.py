"""Module to take readings from DHT22 and report them to HA."""

from __future__ import annotations

from enum import IntEnum
from logging import getLogger
from os import environ
from time import sleep
from typing import TYPE_CHECKING, Any, Final

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from pigpio import EITHER_EDGE  # type: ignore[import-untyped]
from pigpio import pi as rasp_pi
from wg_utilities.decorators import process_exception
from wg_utilities.functions import backoff
from wg_utilities.loggers import add_stream_handler

if TYPE_CHECKING:
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")

add_stream_handler(LOGGER)

MQTT = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
MQTT.username_pw_set(username=environ["MQTT_USERNAME"], password=environ["MQTT_PASSWORD"])

MQTT_HOST: Final[str] = environ["MQTT_HOST"]

PI = rasp_pi()

SOLENOID: Final[int] = 26
MQTT_TOPIC = environ["DEHUMIDIFIER_CONTROLLER_MQTT_TOPIC"]

ON_VALUES = (True, 1, "1", "on", "true")
OFF_VALUES = (False, 0, "0", "off", "false")


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

    MQTT.publish(MQTT_TOPIC, bool(state))

    LOGGER.info("Published state '%s' to topic '%s'", state, MQTT_TOPIC)


@MQTT.message_callback()
def on_message(_: Any, __: Any, message: mqtt.MQTTMessage) -> None:
    """Process env vars on MQTT message.

    Args:
        message (MQTTMessage): the message object from the MQTT subscription
    """

    if (value := message.payload.decode().casefold()) not in ON_VALUES + OFF_VALUES:
        raise ValueError(
            f"Invalid value received ({value}). Must be one of: "
            f"{ON_VALUES + OFF_VALUES}"
        )

    LOGGER.info("Received message: %s", value)

    PI.write(SOLENOID, level=True)
    sleep(1)
    PI.write(SOLENOID, level=False)


@MQTT.connect_callback()
def on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: mqtt.ConnectFlags,
    rc: ReasonCode,
    properties: Properties | None,
) -> None:
    """Callback for when the MQTT client connects."""
    _ = client, userdata, flags, properties

    if rc == 0:
        LOGGER.info("Connected to MQTT broker")
    else:
        LOGGER.error("Failed to connect to MQTT broker: %s", rc)


@MQTT.disconnect_callback()
def on_disconnect(
    client: mqtt.Client,
    userdata: Any,
    flags: mqtt.DisconnectFlags,
    rc: ReasonCode,
    properties: Properties | None,
) -> None:
    """Callback for when the MQTT client disconnects."""
    _ = client, userdata, flags, properties

    if rc != 0:
        LOGGER.error("Unexpected disconnection from MQTT broker: %r", rc)
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

    if level == NewPinState.ON:
        # Safety feature to prevent the solenoid from being on for too long
        sleep(5)
        PI.write(SOLENOID, level=False)


@process_exception(logger=LOGGER)
def main() -> None:
    """Main function."""
    MQTT.connect(MQTT_HOST)

    MQTT.subscribe(MQTT_TOPIC)

    PI.callback(SOLENOID, EITHER_EDGE, pin_callback)

    PI.write(SOLENOID, level=False)

    MQTT.loop_forever()


if __name__ == "__main__":
    main()
