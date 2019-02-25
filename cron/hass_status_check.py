from datetime import datetime
from os import getenv, path, makedirs
from subprocess import Popen, PIPE
from time import sleep, time

from dotenv import load_dotenv
from requests import get
from requests.exceptions import ReadTimeout
from wg_utilities.helpers.functions import get_proj_dirs, pb_notify
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME

PROJECT_DIR, SECRET_FILES_DIR, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)

NOW = datetime.now()

load_dotenv(ENV_FILE)

LOG_DIR = '{}logs/'.format(PROJECT_DIR)

HASS_LOCAL_IP = getenv('HASSPI_LOCAL_IP')
HASS_PORT = getenv('HASS_PORT')

PB_PARAMS = {
    'token': getenv('PB_API_KEY'),
    't': 'Home Assistant Status Check'
}


# TODO create central logging location
def log(m='', newline=False):
    if not path.isdir(LOG_DIR):
        makedirs(LOG_DIR)

    with open('{}hass_status_{}-{:02d}-{:02d}.log'.format(LOG_DIR, NOW.year, NOW.month, NOW.day), 'a') as f:
        if newline:
            f.write('\n')
        f.write('\n[{}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}]: {}'
                .format(NOW.year, NOW.month, NOW.day, NOW.hour, NOW.minute, NOW.second, m)
                )


def main():
    log('Running status check. http://{}:{}'.format(HASS_LOCAL_IP, HASS_PORT), newline=True)
    start_time = time()
    server_unresponsive = True

    while server_unresponsive:
        try:
            req = get('http://{}:{}'.format(HASS_LOCAL_IP, HASS_PORT), timeout=5)
            message = 'Server response: {} - {}'.format(req.status_code, req.reason)
            if not req.status_code == 200:
                pb_notify(m=message, **PB_PARAMS)
                raise ReadTimeout
            else:
                log(message)
            server_unresponsive = False
        except Exception as e:
            log(str(e))
            pb_notify(m='Web server currently unresponsive. Attempting service restart.', **PB_PARAMS)

            Popen(['sudo', 'systemctl', 'restart', 'home-assistant@homeassistant.service'], stdout=PIPE, stderr=PIPE)
            sleep(30)
            if (time() - start_time) > 240:
                pb_notify(m='Restart attempt time elapsed > 4 minutes. Rebooting pi.', **PB_PARAMS)
                log('Rebooting pi')
                log()
                Popen(['sudo', 'reboot'], stdout=PIPE, stderr=PIPE)


if __name__ == '__main__':
    main()
