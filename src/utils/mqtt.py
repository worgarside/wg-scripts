"""MQTT utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import paho.mqtt.client
from paho.mqtt.enums import CallbackAPIVersion
from wg_utilities.functions import backoff
from wg_utilities.loggers import get_streaming_logger

from . import const

if TYPE_CHECKING:
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode

CLIENT = paho.mqtt.client.Client(callback_api_version=CallbackAPIVersion.VERSION2)
CLIENT.username_pw_set(username=const.MQTT_USERNAME, password=const.MQTT_PASSWORD)

_LOGGER = get_streaming_logger(__name__)


@CLIENT.connect_callback()
def on_connect(
    client: paho.mqtt.client.Client,
    userdata: Any,
    flags: paho.mqtt.client.ConnectFlags,
    rc: ReasonCode,
    properties: Properties | None,
) -> None:
    """Callback for when the MQTT client connects."""
    _ = client, userdata, flags, properties

    if rc == 0:
        _LOGGER.info("Connected to MQTT broker")
    else:
        _LOGGER.error("Failed to connect to MQTT broker: %s", rc)


@CLIENT.disconnect_callback()
def on_disconnect(
    client: paho.mqtt.client.Client,
    userdata: Any,
    flags: paho.mqtt.client.DisconnectFlags,
    rc: ReasonCode,
    properties: Properties | None,
) -> None:
    """Callback for when the MQTT client disconnects."""
    _ = client, userdata, flags, properties

    if rc != 0:
        _LOGGER.error("Unexpected disconnection from MQTT broker: %r", rc)
        backoff_reconnect()


@backoff(logger=_LOGGER, max_delay=10, timeout=120)
def backoff_reconnect() -> None:
    """Reconnect to the MQTT broker."""
    CLIENT.reconnect()


__all__ = ["CLIENT"]
