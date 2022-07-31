"""Home Assistant webhooks"""
from os import getenv

from dotenv import load_dotenv
from psutil import sensors_battery
from requests import post
from requests.exceptions import RequestException
from wg_utilities.exceptions import on_exception  # pylint: disable=no-name-in-module

load_dotenv()

HASS_BASE_URL = getenv("HASS_BASE_URL")


@on_exception()  # type: ignore[misc]
def update_battery_percentage_sensor() -> None:
    """Send MacBook battery info to Home Assistant"""
    try:
        res = post(
            f"{HASS_BASE_URL}/api/webhook/will_s_macbook_pro_battery_percentage",
            json={
                "battery_percentage": sensors_battery().percent,
                "battery_seconds_left": sensors_battery().secsleft,
                "power_plugged": sensors_battery().power_plugged,
            },
            headers={"Content-Type": "application/json"},
        )
        print(res.status_code, res.reason)
    except (ConnectionError, RequestException):
        pass


if __name__ == "__main__":
    update_battery_percentage_sensor()
