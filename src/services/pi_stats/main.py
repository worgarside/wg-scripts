"""This script sends system stats to HA for use in system health stuff."""

from __future__ import annotations

import socket
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from json import dumps
from os import getenv, getloadavg
from pathlib import Path
from threading import Event
from time import sleep, time
from typing import TYPE_CHECKING, ClassVar, Final, TypedDict

import psutil
from wg_utilities.decorators import process_exception
from wg_utilities.functions import run_cmd
from wg_utilities.loggers import get_streaming_logger
from wg_utilities.utils import mqtt

from services.pi_stats.discovery import (
    PAYLOAD_OFFLINE,
    PAYLOAD_ONLINE,
    availability_topic,
    build_discovery_updates,
    discovery_topic,
    disk_path_slugs,
    load_component_ids,
    save_component_ids,
    stats_topic,
)
from wg_scripts import __version__

if TYPE_CHECKING:
    from paho.mqtt.client import Client, ConnectFlags, MQTTMessageInfo
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode

LOGGER = get_streaming_logger(__name__)

# =============================================================================
# Constants

IP_FALLBACK: Final = f"{mqtt.HOSTNAME}.local"
ONE_MINUTE: Final = 60

SERVICE_START_TIME: Final = datetime.now(UTC).isoformat()

DISK_USAGE_PATHS: Final[tuple[str, ...]] = tuple(
    path.strip()
    for path in getenv("DISK_USAGE_PATHS", "/home").split(",")
    if path.strip()
)

AVAILABILITY_TOPIC: Final = availability_topic(mqtt.HOSTNAME)
DISCOVERY_TOPIC: Final = discovery_topic(mqtt.HOSTNAME)
DISCOVERY_STATE_PATH: Final = Path(
    getenv(
        "PI_STATS_DISCOVERY_STATE_PATH",
        str(Path.home() / ".cache/wg-scripts/pi_stats-discovery-components.json"),
    ),
)
PUBLISH_TIMEOUT_SECONDS: Final = 5

# Set from on_connect; consumed on the main thread so wait_for_publish cannot deadlock
# the Paho network loop.
_DISCOVERY_NEEDED: Final = Event()


class Stats(TypedDict):
    """Type definition for the stats dictionary."""

    cpu_usage: float
    memory_usage: float
    temperature: float
    disk_usage: dict[str, float]
    load_1m: float
    load_5m: float
    load_15m: float
    uptime: int
    boot_time: str
    local_git_ref: str
    active_git_ref: str
    local_ip: str
    service_start_time: str
    wg_scripts_version: str


@lru_cache(maxsize=1)
def local_git_ref() -> str:
    """Get the current git ref for the local repo."""
    output, error = run_cmd("git describe --tags --exact-match", exit_on_error=False)

    if "no tag exactly matches" in error:
        output, _ = run_cmd("git rev-parse --short HEAD")

    return output.strip()


@lru_cache(maxsize=1)
def local_ip() -> str:
    """Get the local IP address of the Pi.

    https://stackoverflow.com/a/28950776/7689800
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)

    ip = IP_FALLBACK

    try:
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
    except Exception:
        LOGGER.exception("Failed to get local IP address")
    finally:
        s.close()

    return str(ip)


@dataclass
class RaspberryPi:
    """Class to represent a Pi and its current statistics."""

    ACTIVE_GIT_REF: ClassVar[str] = local_git_ref()

    STATS_TOPIC: ClassVar[str] = stats_topic(mqtt.HOSTNAME)

    boot_time: float = field(default_factory=psutil.boot_time)
    boot_time_iso: str = field(init=False)

    get_count: int = 0

    def get_stats(self) -> Stats:
        """Get the current stats for the Pi.

        Returns:
            Stats: the current stats for the Pi.
        """
        # Doing this first and separately so the other properties don't affect the
        # readings
        load_1m, load_5m, load_15m = self.load_averages

        cpu_usage, memory_usage, temperature, uptime = (
            self.cpu_usage,
            self.memory_usage,
            self.cpu_temp,
            self.uptime,
        )

        if self.get_count % 5 == 0:
            local_git_ref.cache_clear()
            local_ip.cache_clear()

            self.boot_time = psutil.boot_time()
            self.boot_time_iso = datetime.fromtimestamp(
                self.boot_time,
                tz=UTC,
            ).isoformat()
        elif local_ip() == IP_FALLBACK:
            local_ip.cache_clear()

        self.get_count += 1

        return Stats(
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            temperature=temperature,
            disk_usage=self.disk_usage,
            load_1m=load_1m,
            load_5m=load_5m,
            load_15m=load_15m,
            uptime=uptime,
            boot_time=self.boot_time_iso,
            local_git_ref=local_git_ref(),
            active_git_ref=self.ACTIVE_GIT_REF,
            local_ip=local_ip(),
            service_start_time=SERVICE_START_TIME,
            wg_scripts_version=__version__,
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
    def disk_usage(self) -> dict[str, float]:
        """Get the current disk usage percentage for each configured path.

        Returns:
            dict[str, float]: path to usage percentage mapping. Unavailable paths
            are omitted for this sample.
        """
        usage: dict[str, float] = {}

        for path in DISK_USAGE_PATHS:
            try:
                usage[path] = float(round(psutil.disk_usage(path).percent, 2))
            except OSError:
                LOGGER.exception("Failed to get disk usage for %s", path)

        return usage

    @property
    def memory_usage(self) -> float:
        """Get the current memory usage percentage.

        Returns:
            float: the percentage of memory currently in use.
        """
        return float(round(psutil.virtual_memory().percent, 2))

    @property
    def cpu_usage(self) -> float:
        """Get the current CPU usage percentage.

        Returns:
            float: the percentage of CPU currently in use.
        """
        return float(round(psutil.cpu_percent(), 2))

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
        return int(time() - self.boot_time)


def publish_discovery(client: Client) -> None:
    """Publish retained MQTT device discovery, including removal tombstones.

    Must run on the main thread (not inside a Paho callback): QoS 1 acks are
    processed by the network loop, so ``wait_for_publish`` from ``on_connect``
    would deadlock.
    """
    previous_component_ids = load_component_ids(DISCOVERY_STATE_PATH)
    payloads = build_discovery_updates(
        mqtt.HOSTNAME,
        DISK_USAGE_PATHS,
        previous_component_ids,
    )

    for payload in payloads:
        message = client.publish(
            topic=DISCOVERY_TOPIC,
            payload=dumps(payload),
            retain=True,
            qos=1,
        )
        message.wait_for_publish(timeout=PUBLISH_TIMEOUT_SECONDS)
        if not message.is_published():
            raise TimeoutError(
                f"Discovery publish to {DISCOVERY_TOPIC} was not acknowledged",
            )

    clean_payload = payloads[-1]
    component_ids = set(clean_payload["cmps"])
    save_component_ids(DISCOVERY_STATE_PATH, component_ids)
    LOGGER.info(
        "Published MQTT discovery for %s (%d components, %d updates) to %s",
        mqtt.HOSTNAME,
        len(clean_payload["cmps"]),
        len(payloads),
        DISCOVERY_TOPIC,
    )


def publish_availability(client: Client, payload: str) -> MQTTMessageInfo:
    """Publish retained online/offline availability for pi_stats."""
    return client.publish(
        topic=AVAILABILITY_TOPIC,
        payload=payload,
        retain=True,
        qos=1,
    )


def on_connect(
    client: Client,
    _userdata: object,
    _connect_flags: ConnectFlags,
    reason_code: ReasonCode,
    _properties: Properties | None,
) -> None:
    """Restore availability after every successful connection; schedule discovery."""
    if reason_code.is_failure:
        LOGGER.error("MQTT connection failed: %s", reason_code)
        return

    LOGGER.info("Connected to MQTT broker")

    # Keep availability independent of discovery so a cache/publish failure cannot
    # leave entities stuck unavailable after an LWT offline.
    try:
        publish_availability(client, PAYLOAD_ONLINE)
    except Exception:
        LOGGER.exception("Failed to publish MQTT availability after connecting")

    _DISCOVERY_NEEDED.set()


def publish_discovery_if_needed(client: Client) -> None:
    """Publish discovery from the main thread when a connection requested it."""
    if not _DISCOVERY_NEEDED.is_set() or not client.is_connected():
        return

    _DISCOVERY_NEEDED.clear()
    try:
        publish_discovery(client)
    except Exception:
        LOGGER.exception("Failed to publish MQTT discovery after connecting")


def shutdown(client: Client) -> None:
    """Flush offline availability before disconnecting cleanly."""
    message = publish_availability(client, PAYLOAD_OFFLINE)
    try:
        message.wait_for_publish(timeout=PUBLISH_TIMEOUT_SECONDS)
        if message.is_published():
            client.disconnect()
        else:
            LOGGER.warning(
                "Offline availability was not acknowledged; relying on MQTT last will",
            )
    finally:
        client.loop_stop()


@process_exception(logger=LOGGER)
def main() -> None:
    """Sends system stats to Home Assistant every minute."""
    # Fail fast on bad DISK_USAGE_PATHS before touching the broker.
    disk_path_slugs(DISK_USAGE_PATHS)

    rasp_pi = RaspberryPi()

    # Last will must be set before connecting so abrupt exits mark the service offline.
    mqtt.CLIENT.will_set(
        topic=AVAILABILITY_TOPIC,
        payload=PAYLOAD_OFFLINE,
        qos=1,
        retain=True,
    )
    mqtt.CLIENT.on_connect = on_connect

    mqtt.CLIENT.connect(mqtt.MQTT_HOST)
    mqtt.CLIENT.loop_start()

    for _ in range(120):
        if mqtt.CLIENT.is_connected():
            break

        LOGGER.info("Waiting for connection to MQTT broker...")
        sleep(1)

    if not mqtt.CLIENT.is_connected():
        LOGGER.error("Failed to connect to MQTT broker, exiting")
        raise SystemExit(1)

    try:
        # This is done as a while loop, rather than a cron job, so that instantiating
        # the pi etc. every time doesn't influence the readings
        with suppress(KeyboardInterrupt):
            while True:
                publish_discovery_if_needed(mqtt.CLIENT)

                if not mqtt.CLIENT.is_connected():
                    sleep(1)
                    continue

                try:
                    mqtt.CLIENT.publish(
                        topic=rasp_pi.STATS_TOPIC,
                        payload=dumps(rasp_pi.get_stats()),
                        retain=False,
                        qos=1,
                    )
                except TimeoutError:
                    LOGGER.exception(
                        "%s timed out sending stats, exiting",
                        mqtt.HOSTNAME,
                    )
                    raise SystemExit from None

                # Chunk the interval so reconnect discovery runs promptly.
                for _ in range(ONE_MINUTE):
                    if _DISCOVERY_NEEDED.is_set() or not mqtt.CLIENT.is_connected():
                        break
                    sleep(1)
    finally:
        with suppress(Exception):
            shutdown(mqtt.CLIENT)

    LOGGER.info("Disconnected from MQTT broker, exiting")
    raise SystemExit


if __name__ == "__main__":
    main()
