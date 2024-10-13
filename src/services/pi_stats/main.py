"""This script sends system stats to HA for use in system health stuff."""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from json import dumps
from os import getloadavg
from time import sleep, time
from typing import ClassVar, Final, TypedDict

import psutil
from wg_utilities.decorators import process_exception
from wg_utilities.functions import run_cmd
from wg_utilities.loggers import get_streaming_logger
from wg_utilities.utils import mqtt

LOGGER = get_streaming_logger(__name__)

# =============================================================================
# Constants

IP_FALLBACK: Final = f"{mqtt.HOSTNAME}.local"
ONE_MINUTE: Final = 60

SERVICE_START_TIME: Final = datetime.now(UTC).isoformat()


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
    local_ip: str
    service_start_time: str


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

    STATS_TOPIC: ClassVar[str] = f"/homeassistant/{mqtt.HOSTNAME}/stats"

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
            disk_usage_percent=self.disk_usage_percent,
            load_1m=load_1m,
            load_5m=load_5m,
            load_15m=load_15m,
            uptime=uptime,
            boot_time=self.boot_time_iso,
            local_git_ref=local_git_ref(),
            active_git_ref=self.ACTIVE_GIT_REF,
            local_ip=local_ip(),
            service_start_time=SERVICE_START_TIME,
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
        return float(round(psutil.disk_usage("/home").percent, 2))

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


@process_exception(logger=LOGGER)
def main() -> None:
    """Sends system stats to Home Assistant every minute."""
    rasp_pi = RaspberryPi()

    mqtt.CLIENT.connect(mqtt.MQTT_HOST)
    mqtt.CLIENT.loop_start()

    while not mqtt.CLIENT.is_connected():
        LOGGER.info("Waiting for connection to MQTT broker...")
        sleep(1)

    # This is done as a while loop, rather than a cron job, so that instantiating the
    # pi etc. every time doesn't influence the readings
    while mqtt.CLIENT.is_connected():
        try:
            mqtt.CLIENT.publish(
                topic=rasp_pi.STATS_TOPIC,
                payload=dumps(rasp_pi.get_stats()),
                retain=False,
                qos=1,
            )
        except TimeoutError:
            LOGGER.exception("%s timed out sending stats, exiting", mqtt.HOSTNAME)
            raise SystemExit from None

        sleep(ONE_MINUTE)

    LOGGER.info("Disconnected from MQTT broker, exiting")
    raise SystemExit


if __name__ == "__main__":
    main()
