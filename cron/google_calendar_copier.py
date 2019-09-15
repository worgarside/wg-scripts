import os
import pickle
from datetime import datetime, timedelta
from enum import Enum, auto

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar.events']

SECRET_FILES_DIR = str('/'.join(
    str(os.path.dirname(__file__).replace('\\', '/')).split('/')[:-1] + ['secret_files', 'calendar_copier', '']
))

CLIENT_SECRETS_PATH = f'{SECRET_FILES_DIR}client_id.json'

SRC_TOKEN = f'{SECRET_FILES_DIR}work_token.pickle'
DEST_TOKEN = f'{SECRET_FILES_DIR}personal_token.pickle'

DESCRIPTION_SUFFIX = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Copied from work calendar."


class CalendarType(Enum):
    SOURCE = auto()
    DEST = auto()


def authenticate(calendar):
    if calendar == CalendarType.SOURCE:
        token_path = SRC_TOKEN
    elif calendar == CalendarType.DEST:
        token_path = DEST_TOKEN
    else:
        raise TypeError(f'Invalid argument passed as calendar: {calendar}')

    creds = None

    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)

    return service


def get_events(calendar, event_count=250, from_dttm=None, to_dttm: datetime = None):
    service = authenticate(calendar)

    from_dttm = datetime.utcnow().isoformat() + 'Z' if not from_dttm else from_dttm  # 'Z' indicates UTC time
    to_dttm = (datetime.utcnow() + timedelta(days=365)).isoformat() + 'Z' if not to_dttm \
        else (to_dttm.utcnow() + timedelta(days=365)).isoformat() + 'Z'

    events_result = service.events().list(
        calendarId='primary',
        timeMin=from_dttm,
        timeMax=to_dttm,
        maxResults=event_count,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    return events_result.get('items', [])


def create_event(event, service=None, calendar=None):
    service = authenticate(calendar) if not service else service

    event_key_whitelist = ['description', 'end', 'location', 'start', 'summary']

    new_event = {key: event[key] for key in event_key_whitelist if key in event}

    new_event['colorId'] = 8

    service.events().insert(calendarId='primary', body=new_event).execute()


def event_in_list(target_event, event_list):
    match_keys = ['description', 'end', 'location', 'start', 'summary']
    for e in event_list:
        for k in match_keys:
            if k in e and k in target_event and e[k] == target_event[k]:
                return True

    return False


def main():
    event_count = 20

    source_events = get_events(CalendarType.SOURCE, event_count=event_count)
    destination_events = get_events(CalendarType.DEST)

    service = authenticate(CalendarType.DEST)
    print('Adding:')
    for e in source_events:
        if e['summary'].lower() == 'out of office':
            continue

        e['description'] = f"{e['description']}\n\n{DESCRIPTION_SUFFIX}" if 'description' in e \
            else DESCRIPTION_SUFFIX

        if not event_in_list(e, destination_events) and \
                (
                        (
                                'attendees' in e and
                                [a['responseStatus'] for a in e['attendees'] if 'self' in a and a['self']]
                                [0].lower() in ['accepted', 'tentative', 'needsAction']
                        ) or 'attendees' not in e
                ):
            print(f"    {e['summary']}")
            create_event(e, service=service)

    print('\nDeleting:')
    for e in destination_events:
        if 'description' in e and e['description'].endswith(' - Copied from work calendar.') and \
                not event_in_list(e, source_events):
            service.events().delete(calendarId='primary', eventId=e['id']).execute()
            print(f"    {e['summary']}")


if __name__ == '__main__':
    main()
