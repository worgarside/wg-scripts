from json import dump, load
from os import getenv, path
from time import strptime, strftime, mktime, time, sleep
from os import listdir
from traceback import format_exc

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from wg_utilities.helpers.functions import get_proj_dirs, pb_notify, exponential_backoff
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME

PROJECT_DIR, SECRET_FILES_DIR, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)

load_dotenv(ENV_FILE)

PB_PARAMS = {
    'token': getenv('PB_API_KEY'),
    't': 'Octoprint Notification'
}

CREDENTIALS_FILE = '{}google_credentials.json'.format(SECRET_FILES_DIR)
TIMELAPSE_DIR = '/home/pi/.octoprint/timelapse/'

API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
MAX_RETRIES = 10


def output(m: str = ''):
    # TODO import from wg-utilities
    from sys import stdout
    try:
        print(m)
        stdout.flush()
        # pb_notify(m=m, **PB_PARAMS)
    except Exception as e:
        print(e)


def _get_client():
    with open(CREDENTIALS_FILE, 'r') as f:
        credentials_dict = load(f)

    updated_credentials = Credentials(
        credentials_dict['token'],
        credentials_dict['refresh_token'],
        '',
        credentials_dict['token_uri'],
        credentials_dict['client_id'],
        credentials_dict['client_secret'],
        credentials_dict['scopes']
    )

    with open(CREDENTIALS_FILE, 'w') as f:
        dump({'token': updated_credentials.token,
              'refresh_token': updated_credentials.refresh_token,
              'token_uri': updated_credentials.token_uri,
              'client_id': updated_credentials.client_id,
              'client_secret': updated_credentials.client_secret,
              'scopes': updated_credentials.scopes}, f)

    return build(API_SERVICE_NAME, API_VERSION, credentials=updated_credentials, cache_discovery=False)


def initialize_upload(yt_client, video_file, metadata):
    body = {
        'snippet': {
            'title': metadata['video_title'],
            'description': metadata['description'],
        },
        'status': {
            'privacyStatus': metadata['privacy_status']
        }
    }

    insert_request = yt_client.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=MediaFileUpload(video_file, chunksize=-1, resumable=True)
    )

    def upload_video():
        status, response = insert_request.next_chunk()

        if 'id' in response:
            pb_notify(t='Octolapse uploaded',
                      m="Octolapse '{}' successfully uploaded: https://youtu.be/{}"
                      .format(metadata['video_title'], response['id']),
                      token=PB_PARAMS['token`']
                      )
        else:
            pb_notify('The upload failed with an unexpected response: {}'.format(response), **PB_PARAMS)
            exit()

        return status, response

    output('Starting EB upload')

    exponential_backoff(upload_video)


def main(**kwargs):
    printed_file = kwargs['file'].replace('.gcode', '') if 'file' in kwargs else None

    if not printed_file:
        pb_notify(m='File not in kwargs', **PB_PARAMS)

    pb_notify(m=f'{printed_file} successfully printed. Upload pending.', **PB_PARAMS)

    matched_timelapses = None
    retry = 0
    while not matched_timelapses:
        retry += 1
        if retry > MAX_RETRIES:
            pb_notify(f'No timelapse found for {printed_file}', **PB_PARAMS)
            exit()
            # TODO graceful exit
        sleep(10)
        matched_timelapses = [file for file in listdir(TIMELAPSE_DIR) if printed_file in file]

    latest_timelapse_file = sorted(matched_timelapses, key=lambda x: x[-18:-4])[-1] \
        if len(matched_timelapses) > 1 else matched_timelapses[0]

    timelapse_date = strptime(latest_timelapse_file[-18:-4], '%Y%m%d%H%M%S')

    hours_since_timelapse = (time() - mktime(timelapse_date)) / 3600

    if hours_since_timelapse > 1.5:
        pb_notify('Too long since timelapse, might be an older one?', **PB_PARAMS)
        exit()
        #  TODO: exit gracefully, think about timing

    metadata = {
        'video_title': '{} on Prusa Mk3 | {}'.format(latest_timelapse_file[:-19].replace('_', ' ').title(),
                                                     strftime('%H:%M %d/%m/%Y', timelapse_date))
    }

    try:
        metadata['description'] = 'Filmed with Octolapse on a Pi Camera v2. ' \
                                  'Automatically uploaded post-render through custom scripts.'
        metadata['privacy_status'] = 'unlisted'

        initialize_upload(_get_client(), TIMELAPSE_DIR + latest_timelapse_file, metadata)
    except Exception as e:
        output(format_exc())
        print(e)
    # sleep(1800)
#

def user_help():
    """
    A helper function which outputs any extra information about your script as well as returns expected args
    :returns: a dictionary of argument keys and descriptions to be printed in the same way by every script
    """
    author = 'Will Garside'
    description = "Uploads a timelapse to YouTube when it's completed by Octoprint"
    expected_args = {
        '--file': 'Name of file to be uploaded'
    }
    env_list = {}

    return author, description, expected_args, env_list


if __name__ == '__main__':
    main()
