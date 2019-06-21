from os import getenv, path
from time import sleep

from dotenv import load_dotenv
from requests import get
from requests.exceptions import ReadTimeout
from wg_utilities.helpers.functions import get_proj_dirs
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME
from wg_utilities.services.services import pb_notify

_, _, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)

load_dotenv(ENV_FILE)

PB_PARAMS = {
    'token': getenv('PB_API_KEY'),
    't': 'Serveo Status Check'
}


def main():
    req = None
    msg_base = "serveo.net currently unavailable. "
    failed = False
    send_pb_notification = True

    while not req or not req.status_code == 200:
        try:
            req = get('http://serveo.net', timeout=10)
            assert req.status_code == 200, f"Status code is {req.status_code}."
        except ReadTimeout:
            failed = True
            msg = msg_base + "No response returned."
            print(msg)
            if send_pb_notification:
                pb_notify(m=msg, **PB_PARAMS)

            send_pb_notification = not send_pb_notification
        except AssertionError as err:
            failed = True
            msg = msg_base + str(err)
            print(msg)
            if send_pb_notification:
                pb_notify(m=msg, **PB_PARAMS)

            send_pb_notification = not send_pb_notification

        sleep(15 * 60)

    if failed:
        pb_notify(m="serveo.net back up now :)")


if __name__ == '__main__':
    main()
