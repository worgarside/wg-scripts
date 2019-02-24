from git import Repo

WG_UTILS_DIR = '/home/pi/Projects/wg-utils'


def main():
    repo = Repo(WG_UTILS_DIR)
    print('Pulling from Git...')
    repo.remotes.origin.pull()
    print('Done!')


def user_help():
    """
    A helper function which outputs any extra information about your script as well as returns expected args
    :returns: a dictionary of argument keys and descriptions to be printed in the same way by every script
    """
    author = 'Will Garside'
    description = 'Updates core files in wg-utils'
    expected_args = {}
    env_list = {}

    return author, description, expected_args, env_list


if __name__ == '__main__':
    main()
