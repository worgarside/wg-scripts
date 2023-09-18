"""Home Assistant webhooks."""
from __future__ import annotations

from json import dumps
from logging import DEBUG, getLogger
from os import getenv
from pathlib import Path

from dotenv import load_dotenv
from psutil import sensors_battery
from requests import post
from requests.exceptions import RequestException
from wg_utilities.exceptions import on_exception
from wg_utilities.loggers import add_file_handler, add_stream_handler

load_dotenv()

HASS_BASE_URL = getenv("HASS_BASE_URL")

LOGGER = getLogger(__name__)
LOGGER.setLevel(DEBUG)
add_stream_handler(LOGGER)
add_file_handler(
    LOGGER, logfile_path=Path.home() / "logs" / "wg-scripts" / "hass_webhooks.log"
)


@on_exception(
    ignore_exception_types=(ConnectionError, RequestException),
    _suppress_ignorant_warnings=True,
)
def update_battery_percentage_sensor() -> None:
    """Send MacBook battery info to Home Assistant."""

    payload = {
        "battery_percentage": sensors_battery().percent,  # type: ignore[no-untyped-call]
        "battery_seconds_left": sensors_battery().secsleft,  # type: ignore[no-untyped-call]
        "power_plugged": sensors_battery().power_plugged,  # type: ignore[no-untyped-call]
    }

    LOGGER.info("Sending battery info to Home Assistant: %s", dumps(payload))

    res = post(
        f"{HASS_BASE_URL}/api/webhook/will_s_macbook_pro_battery_percentage",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
    )
    LOGGER.debug("Response: %s %s", res.status_code, res.reason)


if __name__ == "__main__":
    update_battery_percentage_sensor()
