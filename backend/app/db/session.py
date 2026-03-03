"""Database session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL
from app.db.models import Base

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Session:
    return SessionLocal()


def init_db() -> None:
    """Create tables if they don't exist. Tables are managed by init.sql; this is for model sync if needed."""
    Base.metadata.create_all(bind=engine)
