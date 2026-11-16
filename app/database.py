"""
Database connection setup - PostgreSQL via SQLAlchemy.
Local dev connection string below; production will use environment
variables instead of a hardcoded password.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:devpassword@localhost:5432/infinia_labour"
)

# Live (Postgres): room for every request thread to have its own connection (16 Nov 2026 - with the default 5 + 10 a
# busy minute left requests waiting up to 30 s for a connection, and the pages said "working offline"), and a
# connection is tested before use so one dropped by the database never fails a request.
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=30, pool_timeout=10, pool_pre_ping=True, pool_recycle=1800)
else:
    engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
