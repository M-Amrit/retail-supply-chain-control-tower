"""Thin DB helpers. SQLAlchemy is imported lazily so pure-logic modules/tests need no DB driver."""
from functools import lru_cache
from src import config


@lru_cache(maxsize=1)
def get_engine():
    from sqlalchemy import create_engine
    return create_engine(config.DATABASE_URL, pool_pre_ping=True, future=True)


def read_sql(query: str, params: dict | None = None, engine=None):
    import pandas as pd
    from sqlalchemy import text
    with (engine or get_engine()).connect() as c:
        return pd.read_sql(text(query), c, params=params)


def execute(query: str, params: dict | None = None, engine=None):
    from sqlalchemy import text
    with (engine or get_engine()).begin() as c:
        c.execute(text(query), params or {})
