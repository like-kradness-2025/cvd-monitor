"""Background scheduler placeholder."""

from .coinalyze import CoinAlYZeClient
from .database import Database


def run_once() -> None:
    _client = CoinAlYZeClient()
    _db = Database()
    _db.init_schema()
