"""Async SQLite database engine configuration with WAL mode."""

from collections.abc import AsyncIterator
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
import app.db.models  # noqa: F401 - Register models with SQLModel.metadata

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce WAL mode, timeout, and foreign key constraints on SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Initialize database tables and ensure new checkpoint columns exist."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        if "sqlite" in settings.database_url:
            task_cols = (await conn.execute(text("PRAGMA table_info(tasks)"))).fetchall()
            task_col_names = {row[1] for row in task_cols}
            if task_col_names and "messages_json" not in task_col_names:
                await conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN messages_json TEXT NOT NULL DEFAULT '[]'")
                )

            approval_cols = (await conn.execute(text("PRAGMA table_info(approvals)"))).fetchall()
            approval_col_names = {row[1] for row in approval_cols}
            if approval_col_names and "tool_call_id" not in approval_col_names:
                await conn.execute(
                    text("ALTER TABLE approvals ADD COLUMN tool_call_id TEXT NOT NULL DEFAULT ''")
                )


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency that provides an async database session."""
    async with async_session_maker() as session:
        yield session
