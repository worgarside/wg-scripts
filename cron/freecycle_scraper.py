from os import getenv, path
from pickle import load, dump

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests import get
from wg_utilities.helpers.functions import get_proj_dirs, pb_notify
from wg_utilities.references.constants import WGSCRIPTS as PROJ_NAME, BS4_PARSER

PROJECT_DIR, SECRET_FILES_DIR, ENV_FILE = get_proj_dirs(path.abspath(__file__), PROJ_NAME)
PKL_FILE = '{}freecycle_links.pkl'.format(SECRET_FILES_DIR)

load_dotenv(ENV_FILE)

GROUPS = getenv('FREECYCLE_GROUPS').split()
KEYWORDS = set(getenv('FREECYCLE_KEYWORDS').split())

PB_PARAMS = {
    'token': getenv('PB_API_KEY'),
    't': 'Freecycle Alert'
}


def main():
    if not path.isfile(PKL_FILE):
        with open(PKL_FILE, 'wb') as f:
            dump({' '}, f)

    with open(PKL_FILE, 'rb') as f:
        scraped_links = load(f)

    for group in GROUPS:
        table = BeautifulSoup(get(group).content, 'html.parser').findAll('table')

        if not len(table) == 1:
            pb_notify(m=f'Number of tables on page != 1: {len(table)}', **PB_PARAMS)
        else:
            table = table[0]

        rows = table.findAll('tr')

        for item in rows:
            item_link_set = set([a['href'] for a in item.findAll('a', href=True)])

            if not len(item_link_set) == 1:
                pb_notify(m=f'Number of links in row {item} != 1: {len(item_link_set)}', **PB_PARAMS)

            item_link = item_link_set.pop()

            if item_link in scraped_links:
                continue
            else:
                scraped_links.add(item_link)

            item_details = BeautifulSoup(get(item_link).content, BS4_PARSER).find('div', {'id': 'group_post'})

            item_title = ''
            for h2 in item_details.findAll('h2'):
                if 'offer' in h2.text.lower():
                    item_title = h2.text.lower().replace('offer:', '')
                    break

            item_desc = [p.text for p in item_details.findAll('p')]

            item_lookup = set(' '.join(item_desc).split()) | set(item_title.split())

            if KEYWORDS & item_lookup:
                pb_notify(m=f'{item_title.title().strip()}\n\n{item_desc[0].strip()}\n\n{item_link}', **PB_PARAMS)

    with open(PKL_FILE, 'wb') as f:
        dump(scraped_links, f)


if __name__ == '__main__':
    main()
