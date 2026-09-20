"""
Database models.

Uses SQLAlchemy ORM so swapping the database is a one-line change:
- SQLite (default, zero-setup):  DATABASE_URL=sqlite:///./health.db
- PostgreSQL:                    DATABASE_URL=postgresql://user:pass@host/db
- MySQL:                         DATABASE_URL=mysql+pymysql://user:pass@host/db
"""

import os
import uuid
from datetime import datetime

from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./health.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    checks = relationship("SymptomCheck", back_populates="user")


class SymptomCheck(Base):
    """
    Stores each symptom-check a user ran, for their personal history.
    NOTE: this is health data -- see the Security section in README for
    encryption-at-rest and access-control recommendations before storing
    real user data in production.
    """
    __tablename__ = "symptom_checks"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # nullable = anonymous check
    raw_input = Column(Text, nullable=False)
    extracted_symptoms = Column(Text)  # JSON-encoded list
    top_match_id = Column(String)
    top_match_confidence = Column(Float)
    is_emergency_flag = Column(String, default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="checks")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
