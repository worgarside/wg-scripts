from os import getenv, path

from dotenv import load_dotenv
from requests import get
from wg_utilities.helpers.functions import get_proj_dirs, pb_notify
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME

_, _, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)

load_dotenv(ENV_FILE)

PB_PARAMS = {
    'token': getenv('PB_API_KEY'),
    't': 'Serveo Status Check'
}


def main():
    req = None

    try:
        req = get('http://serveo.net', timeout=10)
        if not req.status_code == 200:
            message = f"serveo.net currently unresponsive. {f'Response code: {req.status_code}' if req.status_code else 'No response returned.'}"
            print(message)
            pb_notify(m=message, **PB_PARAMS)
    except Exception:
        message = f"serveo.net currently unresponsive. {f'Response code: {req.status_code}' if req.status_code else 'No response returned.'}"
        print(message)
        pb_notify(m=message, **PB_PARAMS)
        raise


if __name__ == '__main__':
    main()