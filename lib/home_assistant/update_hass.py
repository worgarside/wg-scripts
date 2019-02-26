from os import makedirs, walk
from subprocess import Popen, PIPE

from git import Repo
from wg_utilities.references.constants import HASS_DIR, INDENT

SOURCE_DIR = '/home/pi/hass_config_src/'
GIT_DIR = f'{SOURCE_DIR}.git'


def _compare_files(file1, file2):
    try:
        with open(file1) as f1:
            with open(file2) as f2:
                return f1.read() == f2.read()
    except UnicodeDecodeError:
        with open(file1, 'rb') as f1:
            with open(file2, 'rb') as f2:
                return f1.read() == f2.read()
    except FileNotFoundError:
        return False
    except Exception:
        print(f'#======== Unable to compare the following files ========#\n'
              f'{file1}\n{file2}\n'
              f'#=======================================================#')
        raise


def main():
    core_files = []

    for root, dirs, files in walk(SOURCE_DIR):
        if not root.startswith(GIT_DIR):
            for file in files:
                core_files.append(f"{root[:-1] if root.endswith('/') else root}/{file}")

    repo = Repo(SOURCE_DIR)
    print('Pulling from Git...')
    repo.remotes.origin.pull()

    with open(f'{SOURCE_DIR}.gitignore') as f:
        gitignore_files = set([x.rstrip('\n\r') for x in f.readlines()])

    files_to_copy = [(f, f.replace(SOURCE_DIR, HASS_DIR)) for f in core_files
                     if not _compare_files(f, f.replace(SOURCE_DIR, HASS_DIR))
                     and f not in gitignore_files]
    print(f'{len(files_to_copy)} files to copy\n')

    for source, dest in files_to_copy:
        print(dest.replace(HASS_DIR, ''))
        p = Popen(['cp', source, dest], stdout=PIPE, stderr=PIPE)
        p.wait()
        output, error = p.communicate()
        while error:
            if 'no such file or directory' in error.decode('utf-8').lower():
                directory = '/'.join(error.decode('utf-8').split("'")[1].split('/')[:-1])
                print(f'{INDENT}Creating directory {directory}')
                makedirs(directory)
                p = Popen(['cp', source, dest], stdout=PIPE, stderr=PIPE)
                p.wait()
                output, error = p.communicate()
            else:
                print(error)
                break

    if input('Files copied. Restart home-assistant@homeassistant.service? (Y/n) ').lower() in {'y', ''}:
        Popen(['sudo', 'systemctl', 'restart', 'home-assistant@homeassistant.service'])


def user_help():
    """
    A helper function which outputs any extra information about your script as well as returns expected args
    :returns: a dictionary of argument keys and descriptions to be printed in the same way by every script
    """
    author = 'Will Garside'
    description = 'Updates core files in homeassistant config directory'
    expected_args = {}
    env_list = {}

    return author, description, expected_args, env_list
