from sqlalchemy import create_engine,text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=1800,
)

class Base(DeclarativeBase):
    pass

SessionLocal=sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

def get_db():
    db=SessionLocal()
    
    try:
        yield db
    finally:
        db.close()

   