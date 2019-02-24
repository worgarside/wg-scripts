from json import dump
from os import path
from google_auth_oauthlib.flow import Flow

WGUTILS = 'wg-utils'
DIRNAME, _ = path.split(path.abspath(__file__))
WGUTILS_DIR = DIRNAME[:DIRNAME.find(WGUTILS) + len(WGUTILS)] + '/'
SECRET_FILES_DIR = '{}secret_files/'.format(WGUTILS_DIR)

CLIENT_SECRETS_FILE = '{}google_client_secrets.json'.format(SECRET_FILES_DIR)
CREDENTIALS_FILE = '{}google_credentials.json'.format(SECRET_FILES_DIR)

SCOPES = ['https://www.googleapis.com/auth/youtube',
          'https://www.googleapis.com/auth/youtube.upload']

REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'


def authorize():
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    authorization_url, _ = flow.authorization_url(access_type='offline', include_granted_scopes='true')

    print(authorization_url)
    flow.fetch_token(code=input('Code: ').strip())
    save_credentials(flow.credentials)


def save_credentials(credentials):
    cred_dict = {'token': credentials.token,
                 'refresh_token': credentials.refresh_token,
                 'token_uri': credentials.token_uri,
                 'client_id': credentials.client_id,
                 'client_secret': credentials.client_secret,
                 'scopes': credentials.scopes}

    with open(CREDENTIALS_FILE, 'w') as f:
        dump(cred_dict, f)

        print('Credentials saved: {}'.format(CREDENTIALS_FILE))


def main():
    authorize()


if __name__ == '__main__':
    authorize()
