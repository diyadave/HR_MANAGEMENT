from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings

db_url = settings.DATABASE_URL
engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}

if db_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Conservative pool defaults for burst traffic (e.g. many users clocking in together).
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 40

engine = create_engine(db_url, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
