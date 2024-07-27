"""Module to take readings from DHT22 and report them to HA."""

from __future__ import annotations

import re
import time
from enum import IntEnum
from functools import lru_cache
from json import loads
from logging import WARNING
from os import environ, getenv
from pathlib import Path
from socket import gethostname
from typing import TYPE_CHECKING, Any, Final

import paho.mqtt.client as mqtt
import pigpio  # type: ignore[import-untyped]
from paho.mqtt.enums import CallbackAPIVersion
from wg_utilities.decorators import process_exception
from wg_utilities.functions import backoff
from wg_utilities.loggers import add_warehouse_handler, get_streaming_logger

if TYPE_CHECKING:
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode

LOGGER = get_streaming_logger(__name__)

add_warehouse_handler(LOGGER, level=WARNING)

# =============================================================================
# Constants

ON_VALUES: Final = (True, 1, "1", "on", "true", "True")
OFF_VALUES: Final = (False, 0, "0", "off", "false", "False")

KEBAB_PATTERN = re.compile(r"^(?:[a-z0-9]+-?)+[a-z0-9]+$")
"""Pattern for `kebab-case` strings."""

MAPPING_FILE: Final = Path(__file__).parent / "gpio_mapping.json"

MAPPING: dict[str, int] = loads(MAPPING_FILE.read_text())
"""Mapping of topic suffixes to GPIO pins.

e.g. {"cpu-fan": 17}
"""

PI: Final = pigpio.pi()


NEXT_CHANGE: dict[int, float] = {}
"""Mapping of GPIO pins to the next epoch time they can be changed."""

DISABLE_PIN_CALLBACK: dict[int, bool] = {}
"""Mapping of GPIO pins to whether the next outgoing MQTT message should be suppressed.

Used to stop infinite loops of messages when the pin is changed by the script.
"""

# =============================================================================
# Environment Variables

COOLDOWN: Final = int(getenv("GPIO_COOLDOWN", "5"))
"""Minimum time between pin changes in seconds."""

HOSTNAME: Final = getenv("HOSTNAME", gethostname())
MQTT_USERNAME: Final = getenv("MQTT_USERNAME", HOSTNAME)
MQTT_PASSWORD: Final = environ["MQTT_PASSWORD"]
MQTT_HOST: Final = environ["MQTT_HOST"]

MQTT = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
MQTT.username_pw_set(username=MQTT_USERNAME, password=MQTT_PASSWORD)


class NewPinState(IntEnum):
    """Enum for the possible states of the pin."""

    OFF = 0
    ON = 1
    WATCHDOG_TIMEOUT_NO_CHANGE = 2


@lru_cache(maxsize=len(MAPPING))
def get_topic(pin: int) -> str:
    """Get the topic for a given pin."""
    if not (suffix := next((k for k, v in MAPPING.items() if v == pin), None)):
        raise ValueError(f"Pin {pin} not found in mapping")

    if not KEBAB_PATTERN.fullmatch(suffix):
        raise ValueError(f"Invalid suffix: {suffix}")

    return f"/homeassistant/{HOSTNAME}/gpio/{suffix}"


@lru_cache(maxsize=len(MAPPING))
def get_pin(topic: str) -> int:
    """Get the pin for a given topic."""
    return MAPPING[topic.split("/")[-1]]


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

    LOGGER.info("Received message %r on topic %r", value, message.topic)

    gpio = get_pin(message.topic)
    target_state = value in ON_VALUES

    if bool(PI.read(gpio)) == target_state:
        LOGGER.warning("Pin %i already in state %s", gpio, target_state)
        return

    # Enforce a cooldown period between pin changes
    if (time_to_wait := NEXT_CHANGE.get(gpio, 0) - time.time()) > 0:
        LOGGER.warning("Waiting %.3f seconds before changing pin %i", time_to_wait, gpio)
        time.sleep(time_to_wait)

    LOGGER.info(
        "Setting pin %i (%s) to %s",
        gpio,
        message.topic.split("/")[-1],
        target_state,
    )

    DISABLE_PIN_CALLBACK[gpio] = True

    PI.write(gpio, target_state)


def pin_callback(gpio: int, level: NewPinState, tick: int) -> None:
    """Callback for when the pin changes state."""
    _ = tick

    if level == NewPinState.WATCHDOG_TIMEOUT_NO_CHANGE:
        return

    NEXT_CHANGE[gpio] = time.time() + COOLDOWN

    if DISABLE_PIN_CALLBACK.get(gpio):
        LOGGER.debug("Suppressed outgoing MQTT message for pin %i", gpio)
        DISABLE_PIN_CALLBACK[gpio] = False
        return

    topic = get_topic(gpio)
    payload = bool(level)

    LOGGER.info(
        "GPIO pin %i changed state to %r. Publishing %r to %r; cooldown until %i (%s).",
        gpio,
        level,
        payload,
        topic,
        NEXT_CHANGE[gpio],
        time.ctime(NEXT_CHANGE[gpio]),
    )

    MQTT.publish(topic, payload, retain=True, qos=2)


@process_exception(logger=LOGGER)
def main() -> None:
    """Main function."""
    MQTT.connect(MQTT_HOST)

    topic_suffix_pin_mapping: dict[str, int] = loads(MAPPING_FILE.read_text())

    for pin in topic_suffix_pin_mapping.values():
        topic = get_topic(pin)

        MQTT.subscribe(topic, qos=2)

        LOGGER.info("Subscribed to topic %r", topic)

        PI.callback(pin, pigpio.EITHER_EDGE, pin_callback)

    MQTT.loop_forever()


if __name__ == "__main__":
    main()
