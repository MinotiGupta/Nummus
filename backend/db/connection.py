import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Default to local sqlite if DATABASE_URL not provided
# Railway will provide DATABASE_URL in production
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/razorpay.db")

# Create engine. For SQLite, we need connect_args={"check_same_thread": False}
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
