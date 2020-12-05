from datetime import datetime
from json import load, dump
from logging import StreamHandler, FileHandler, Formatter, getLogger, DEBUG
from os import getenv, mkdir
from os.path import join, abspath, dirname, sep
from pathlib import Path
from pprint import pprint

from dotenv import load_dotenv
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from sys import stdout
from wg_utilities.helpers.functions import get_proj_dirs
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME
from wg_utilities.services.services import pb_notify

LOGGER = getLogger(__name__)
LOGGER.setLevel(DEBUG)

LOG_DIR = f"{Path.home()}/logs/{__file__.split(sep)[-1].split('.')[0]}"

try:
    mkdir(f"{Path.home()}/logs")
except FileExistsError:
    pass

try:
    mkdir(LOG_DIR)
except FileExistsError:
    pass

SH = StreamHandler(stdout)
FH = FileHandler(f"{LOG_DIR}/{datetime.today().strftime('%Y-%m-%d')}.log")

FORMATTER = Formatter(
    "%(asctime)s\t%(name)s\t[%(levelname)s]\t%(message)s", "%Y-%m-%d %H:%M:%S"
)
FH.setFormatter(FORMATTER)
SH.setFormatter(FORMATTER)
LOGGER.addHandler(FH)
LOGGER.addHandler(SH)

PROJECT_DIR, SECRET_FILES_DIR, ENV_FILE = get_proj_dirs(abspath(__file__), PROJ_NAME)

load_dotenv(ENV_FILE)

PB_PARAMS = {"token": getenv("PB_API_KEY"), "t": "Spotify - New Release"}

USER_RECORD_PATH = join(abspath(dirname(__file__)), "user_record.json")
try:
    USER_RECORD = load(open(USER_RECORD_PATH))
except FileNotFoundError:
    USER_RECORD = {"followed_artists": [], "followed_artists_albums": {}}

CLIENT_ID = getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = getenv("SPOTIFY_CLIENT_SECRET")

ALL_SCOPES = [
    "ugc-image-upload",
    "user-read-recently-played",
    "user-top-read",
    "user-read-playback-position",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "app-remote-control",
    "streaming",
    "playlist-modify-public",
    "playlist-modify-private",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-follow-modify",
    "user-follow-read",
    "user-library-modify",
    "user-library-read",
    "user-read-email",
    "user-read-private",
]

SPOTIFY = Spotify(
    auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri="http://localhost:8080",
        scope=",".join(ALL_SCOPES),
    )
)


def get_all(method, output_key=None, *args, **kwargs):
    res = method(*args, **kwargs, limit=50)

    if output_key:
        if output_key not in res:
            raise Exception(
                f"Unable to find `{output_key}` in keys: {','.join(res.keys())}"
            )

        output = res[output_key].get("items", [])

        while after := res[output_key].get("cursors", {}).get("after"):
            res = method(*args, **kwargs, limit=50, after=after)
            output.extend(res[output_key].get("items", []))

        return output

    output = res.get("items", [])

    while after := res.get("cursors", {}).get("after"):
        res = method(*args, **kwargs, limit=50, after=after)

        output.extend(res.get("items", []))

    return output


def get_new_followed_artists():
    LOGGER.info("Getting newly followed artists")

    all_followed_artists = get_all(SPOTIFY.current_user_followed_artists, "artists")

    for artist in all_followed_artists:
        record = {
            "id": artist["id"],
            "name": artist["name"],
        }
        if record not in USER_RECORD["followed_artists"]:
            LOGGER.debug("Adding %s to followed artists", artist["name"])
            USER_RECORD["followed_artists"].append(record)

            USER_RECORD["followed_artists_albums"][artist["id"]] = [
                {"id": album["id"], "name": album["name"]}
                for album in get_all(SPOTIFY.artist_albums, artist_id=artist["id"])
            ]


def check_new_releases():
    LOGGER.info("Checking for new releases for all followed artists")

    for artist in USER_RECORD["followed_artists"]:
        artists_albums = get_all(SPOTIFY.artist_albums, artist_id=artist["id"])

        for album in artists_albums:
            record = {
                "id": album["id"],
                "name": album["name"],
            }

            if record not in USER_RECORD["followed_artists_albums"][artist["id"]]:
                message = f"New album found by {artist['name']}: `{album['name']}`"

                if url := album.get("external_urls", {}).get("spotify"):
                    message += f". {url}"

                LOGGER.info(message)
                USER_RECORD["followed_artists_albums"][artist["id"]].append(
                    record
                )
                pb_notify(message, **PB_PARAMS)


def main():
    get_new_followed_artists()

    check_new_releases()

    LOGGER.info("Updating user record file")
    with open(USER_RECORD_PATH, "w") as fout:
        dump(USER_RECORD, fout, default=str, indent=4)


if __name__ == "__main__":
    main()
