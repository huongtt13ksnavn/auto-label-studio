import json
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "app.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _migrate_class_names() -> None:
    """Migrate legacy `datasets.class_name TEXT` to `class_names JSON list`.

    SQLite has no DDL transactions for column drops pre-3.35, but we can
    add the new column, backfill, and drop the old one with ALTER TABLE
    DROP COLUMN (Python 3.11 ships sqlite >= 3.37).
    """
    insp = inspect(engine)
    if "datasets" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("datasets")}
    if "class_names" in cols and "class_name" not in cols:
        return  # already migrated

    with engine.begin() as conn:
        if "class_names" not in cols:
            conn.execute(text("ALTER TABLE datasets ADD COLUMN class_names TEXT"))
        if "class_name" in cols:
            rows = conn.execute(text("SELECT id, class_name, class_names FROM datasets")).fetchall()
            for row in rows:
                ds_id, legacy, current = row
                if current:
                    continue
                payload = json.dumps([legacy] if legacy else ["object"])
                conn.execute(
                    text("UPDATE datasets SET class_names = :v WHERE id = :id"),
                    {"v": payload, "id": ds_id},
                )
            # SQLite >= 3.35 supports DROP COLUMN
            try:
                conn.execute(text("ALTER TABLE datasets DROP COLUMN class_name"))
            except Exception:
                # leave legacy column in place if SQLite too old; harmless
                pass


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(bind=engine)
    _migrate_class_names()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
