import os
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base


def get_async_url():
    # username = os.getenv("DB_USERNAME")
    # password = os.getenv("DB_PASSWORD")
    # host = os.getenv("DB_HOST")
    # port = os.getenv("DB_PORT")

    return f"sqlite+aiosqlite:///./dev.db"

SQLALCHEMY_ASYNC_DATABASE_URL = get_async_url()

engine = create_async_engine(SQLALCHEMY_ASYNC_DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

Base = declarative_base()