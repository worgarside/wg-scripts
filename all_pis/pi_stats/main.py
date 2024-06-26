"""This script sends system stats to HA for use in system health stuff."""

from __future__ import annotations

import socket
from datetime import datetime
from functools import lru_cache
from json import dumps
from logging import WARNING, getLogger
from os import environ, getloadavg
from time import sleep, time
from typing import TYPE_CHECKING, Any, Final, TypedDict

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from paho.mqtt.enums import CallbackAPIVersion
from psutil import boot_time, cpu_percent, disk_usage, virtual_memory
from wg_utilities.decorators import process_exception
from wg_utilities.functions import backoff, run_cmd
from wg_utilities.loggers import add_stream_handler, add_warehouse_handler

if TYPE_CHECKING:
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")

add_stream_handler(LOGGER)
add_warehouse_handler(LOGGER, level=WARNING)

load_dotenv()

MQTT = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
MQTT.username_pw_set(username=environ["MQTT_USERNAME"], password=environ["MQTT_PASSWORD"])

MQTT_HOST: Final[str] = environ["MQTT_HOST"]

ONE_MINUTE: Final[int] = 60


class Stats(TypedDict):
    """Type definition for the stats dictionary."""

    cpu_usage: float
    memory_usage: float
    temperature: float
    disk_usage_percent: float
    load_1m: float
    load_5m: float
    load_15m: float
    uptime: int
    boot_time: str
    local_git_ref: str
    active_git_ref: str
    local_ip: str | None


@lru_cache(maxsize=1)
def local_git_ref() -> str:
    """Get the current git ref for the local repo."""
    output, error = run_cmd("git describe --tags --exact-match", exit_on_error=False)

    if "no tag exactly matches" in error:
        output, _ = run_cmd("git rev-parse --short HEAD")

    return output.strip()


@lru_cache(maxsize=1)
def local_ip() -> str | None:
    """Get the local IP address of the Pi.

    https://stackoverflow.com/a/28950776/7689800
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)

    try:
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = None
    finally:
        s.close()

    if not ip:
        return None

    return str(ip)


class RaspberryPi:
    """Class to represent a Pi and its current statistics."""

    ACTIVE_GIT_REF: Final[str] = local_git_ref()

    BOOT_TIME: Final[float] = boot_time()
    BOOT_TIME_ISOFORMAT: Final[str] = datetime.fromtimestamp(BOOT_TIME).isoformat()
    HOSTNAME: Final[str] = socket.gethostname()

    STATS_TOPIC: Final[str] = f"/homeassistant/{HOSTNAME}/stats"

    def get_stats(self) -> Stats:
        """Get the current stats for the Pi.

        Returns:
            Stats: the current stats for the Pi.
        """

        # Doing this first and separately so the other properties don't affect the
        # readings
        load_1m, load_5m, load_15m = self.load_averages
        cpu_usage = self.cpu_usage
        memory_usage = self.memory_usage
        temperature = self.cpu_temp
        uptime = self.uptime

        if uptime % 300 < ONE_MINUTE:
            local_git_ref.cache_clear()
            local_ip.cache_clear()

        return Stats(
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            temperature=temperature,
            disk_usage_percent=self.disk_usage_percent,
            load_1m=load_1m,
            load_5m=load_5m,
            load_15m=load_15m,
            uptime=uptime,
            boot_time=self.BOOT_TIME_ISOFORMAT,
            local_git_ref=local_git_ref(),
            active_git_ref=self.ACTIVE_GIT_REF,
            local_ip=local_ip(),
        )

    @property
    def cpu_temp(self) -> float:
        """Get the current CPU temperature.

        Returns:
            float: the current CPU temperature in Celsius.
        """
        output, _ = run_cmd("vcgencmd measure_temp")
        return float(output.replace("temp=", "").replace("'C", ""))

    @property
    def disk_usage_percent(self) -> float:
        """Get the current disk usage percentage.

        Returns:
            float: the current disk usage percentage.
        """
        return float(round(disk_usage("/home").percent, 2))

    @property
    def memory_usage(self) -> float:
        """Get the current memory usage percentage.

        Returns:
            float: the percentage of memory currently in use.
        """
        return float(round(virtual_memory().percent, 2))

    @property
    def cpu_usage(self) -> float:
        """Get the current CPU usage percentage.

        Returns:
            float: the percentage of CPU currently in use.
        """
        return float(round(cpu_percent(), 2))

    @property
    def load_averages(self) -> tuple[float, float, float]:
        """Get the average system load over the last 1, 5, and 15 minutes.

        Returns:
            tuple: average recent system load information.
        """
        return getloadavg()

    @property
    def uptime(self) -> int:
        """Get the current uptime in seconds.

        Returns:
            int: the current uptime in seconds.
        """
        return int(time() - self.BOOT_TIME)


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


@process_exception(logger=LOGGER)
def main() -> None:
    """Sends system stats to Home Assistant every minute."""

    rasp_pi = RaspberryPi()

    MQTT.connect(MQTT_HOST)
    MQTT.loop_start()

    # This is done as a while loop, rather than a cron job, so that instantiating the
    # pi etc. every time doesn't influence the readings
    while True:
        if not MQTT.is_connected():
            LOGGER.warning("MQTT client is not connected. Reconnecting...")
            backoff_reconnect()

        try:
            MQTT.publish(
                rasp_pi.STATS_TOPIC,
                payload=dumps(rasp_pi.get_stats()),
            )
        except TimeoutError:
            LOGGER.exception("%s timed out sending stats", rasp_pi.HOSTNAME)

        sleep(ONE_MINUTE)


if __name__ == "__main__":
    main()
