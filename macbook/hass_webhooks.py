"""Home Assistant webhooks"""
from os import getenv

from requests import post
from dotenv import load_dotenv
from psutil import sensors_battery

load_dotenv()

HASS_BASE_URL = getenv("HASS_BASE_URL")


def update_battery_percentage_sensor():
    """Send MacBook battery info to Home Assistant"""
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


if __name__ == "__main__":
    update_battery_percentage_sensor()
