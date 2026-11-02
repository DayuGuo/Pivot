import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://publishing:publishing_local@127.0.0.1:55432/publishing",
)
if not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("Publishing OS requires PostgreSQL; SQLite is not a verification substitute")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
