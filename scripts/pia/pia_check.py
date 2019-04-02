from os import path, getenv
from subprocess import Popen, PIPE
from time import sleep

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests import get
from wg_utilities.helpers.functions import pb_notify, get_proj_dirs
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME, BS4_PARSER

PROJECT_DIR, SECRET_FILES_DIR, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)

load_dotenv(ENV_FILE)

PIA_URL = 'https://www.privateinternetaccess.com/pages/whats-my-ip/'
WARNING = 'Your private information is exposed'
MAX_VPN_ATTEMPTS = 5

PIA_CONFIG = getenv('PIA_CONFIG_PATH')
PB_PARAMS = {
    'token': getenv('PB_API_KEY'),
    't': 'PIA Alert'
}


def restart_pia():
    stop_process_cmds = 'sudo systemctl stop openvpn_pia.service'.split()
    p = Popen(stop_process_cmds, stdout=PIPE)
    p.wait()
    start_cmds = f'sudo -b /usr/sbin/openvpn {PIA_CONFIG}'.split()

    Popen(start_cmds, stdout=PIPE, stderr=PIPE)


def check_status():
    res = get(PIA_URL)

    if not res.status_code == 200:
        # TODO: replace with Ex Backoff
        exit('Unable to connect to server')

    soup = BeautifulSoup(res.content, BS4_PARSER)
    ip_box = soup.find('div', {'class': 'ipbox-light'})

    return WARNING not in str(ip_box)


def main():
    retry = 0
    notified = False
    while not check_status() and retry < MAX_VPN_ATTEMPTS:
        notified = pb_notify(m='PIA not running, starting restart process', **PB_PARAMS) if not notified else notified

        if not path.isfile(PIA_CONFIG):
            pb_notify(m=f'{PIA_CONFIG} is not a valid file.', **PB_PARAMS)
            break

        retry += 1
        restart_pia()
        sleep(30)

        if check_status():
            pb_notify(m=f"PIA successfully restarted with {retry} attempt{'s' if retry > 1 else ''}.", **PB_PARAMS)
            exit()

    if check_status():
        print('PIA Connected. Starting Deluge daemon.')
        Popen('deluged'.split(), stdout=PIPE)
    else:
        pb_notify(m='Unable to restart PIA. Stopping deluge.', **PB_PARAMS)
        Popen('sudo pkill deluge'.split(), stdout=PIPE)


if __name__ == '__main__':
    main()
