"""This script sends system stats to HA for use in system health stuff."""
from __future__ import annotations

from json import dumps
from logging import WARNING, getLogger
from os import getenv, getloadavg
from pathlib import Path
from socket import gethostname
from time import sleep, time

from dotenv import load_dotenv
from paho.mqtt.publish import single
from psutil import boot_time, cpu_percent, disk_usage, virtual_memory
from wg_utilities.decorators import process_exception
from wg_utilities.functions import run_cmd
from wg_utilities.loggers import add_warehouse_handler

PROJECT_ROOT = Path(__file__).parents[2]

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")

add_warehouse_handler(LOGGER, level=WARNING)

load_dotenv()

MQTT_AUTH_KWARGS = {
    "hostname": getenv("MQTT_HOST"),
    "auth": {
        "username": getenv("MQTT_USERNAME"),
        "password": getenv("MQTT_PASSWORD"),
    },
}


class RaspberryPi:
    """Class to represent a Pi and its current statistics."""

    def __init__(self) -> None:
        self.boot_time = boot_time()
        self.hostname = gethostname()

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
        return int(time() - self.boot_time)


@process_exception(logger=LOGGER)
def main() -> None:
    """Sends system stats to Home Assistant every minute."""

    rasp_pi = RaspberryPi()

    # This is done as a while loop, rather than a cron job, so that instantiating the
    # pi etc. every time doesn't influence the readings
    while True:
        # Doing this first and separately so the other properties don't affect the
        # readings
        load_1m, load_5m, load_15m = rasp_pi.load_averages

        stats = {
            "cpu_usage": rasp_pi.cpu_usage,
            "memory_usage": rasp_pi.memory_usage,
            "temperature": rasp_pi.cpu_temp,
            "disk_usage_percent": rasp_pi.disk_usage_percent,
            "load_1m": load_1m,
            "load_5m": load_5m,
            "load_15m": load_15m,
            "uptime": rasp_pi.uptime,
            "boot_time": rasp_pi.boot_time,
        }

        try:
            single(
                f"/homeassistant/{rasp_pi.hostname}/stats",
                payload=dumps(stats),
                **MQTT_AUTH_KWARGS,  # type: ignore[arg-type]
            )
        except TimeoutError:
            LOGGER.exception("%s timed out sending stats", rasp_pi.hostname)

        sleep(60)


if __name__ == "__main__":
    main()
