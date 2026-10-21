"""Discover 6'6 LoveMachine FMs in Daydream's new-board collection."""
from pathlib import Path
import lovemachine

ORIGIN = 'https://daydreamsurfshop.com'
COLLECTION = ORIGIN + '/collections/new-surfboards'


def fetch_page(page):
    return lovemachine.fetch_page(page, collection=COLLECTION)


def collect(fetch=fetch_page, state=Path('/state/daydream'), now=None):
    return lovemachine.collect(
        fetch=fetch, state=state, now=now, origin=ORIGIN,
        target_sizes={"6'6"}, require_brand=True,
        report_title="Daydream Surf Shop | LoveMachine FM 6'6 inventory")
