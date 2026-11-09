import aiosqlite
import sqlite3
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.config import DATABASE_PATH, DEFAULT_SETTINGS, logger

def init_db_sync():
    """Synchronous database initialization for setup and migrations with safe ALTER TABLE."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # Books Table (Standard Books repository)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            isbn TEXT,
            edition TEXT,
            status TEXT DEFAULT 'pending',
            is_orthodox BOOLEAN DEFAULT 0,
            verified_by TEXT DEFAULT '',
            verification_score REAL DEFAULT 0.0,
            book_category TEXT DEFAULT '',
            verification_reason TEXT DEFAULT '',
            source_channel_title TEXT DEFAULT '',
            normalized_title TEXT DEFAULT '',
            selected_file TEXT,
            confidence REAL DEFAULT 0.0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Books Requested Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS books_requested (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            isbn TEXT,
            edition TEXT,
            status TEXT DEFAULT 'pending',
            is_orthodox BOOLEAN DEFAULT 0,
            verified_by TEXT DEFAULT '',
            verification_score REAL DEFAULT 0.0,
            book_category TEXT DEFAULT '',
            verification_reason TEXT DEFAULT '',
            source_channel_title TEXT DEFAULT '',
            normalized_title TEXT DEFAULT '',
            selected_file TEXT,
            confidence REAL DEFAULT 0.0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Migration helper for newly added columns
        migration_columns = [
            ("is_orthodox", "BOOLEAN DEFAULT 0"),
            ("verified_by", "TEXT DEFAULT ''"),
            ("verification_score", "REAL DEFAULT 0.0"),
            ("book_category", "TEXT DEFAULT ''"),
            ("verification_reason", "TEXT DEFAULT ''"),
            ("source_channel_title", "TEXT DEFAULT ''"),
            ("normalized_title", "TEXT DEFAULT ''"),
        ]

        for table in ["books", "books_requested"]:
            cursor.execute(f"PRAGMA table_info({table})")
            existing_cols = {row[1] for row in cursor.fetchall()}
            for col_name, col_def in migration_columns:
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    logger.info("Migrated table '%s': added column '%s'", table, col_name)

        # Processed and Sent Files Table (Duplicate prevention)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requested_title TEXT NOT NULL,
            author TEXT,
            source TEXT,
            telegram_chat_id INTEGER,
            telegram_message_id INTEGER,
            filename TEXT,
            file_size INTEGER,
            file_hash TEXT,
            confidence REAL,
            status TEXT,
            date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_sent TIMESTAMP
        )
        """)

        # Telegram Sources Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS telegram_sources (
            chat_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT,
            type TEXT,
            enabled INTEGER DEFAULT 1,
            last_searched TIMESTAMP
        )
        """)

        # Settings Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        # Insert default settings if not exists
        for key, val in DEFAULT_SETTINGS.items():
            cursor.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, str(val)))

        conn.commit()
    logger.info("Database initialized and verified successfully at %s", DATABASE_PATH)

async def init_db():
    """Async database initialization."""
    init_db_sync()

@asynccontextmanager
async def get_db_connection():
    """Async context manager for SQLite database connection."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

# Database Helper Functions
async def get_settings() -> Dict[str, Any]:
    async with get_db_connection() as db:
        async with db.execute("SELECT key, value FROM app_settings") as cursor:
            rows = await cursor.fetchall()
            settings = dict(DEFAULT_SETTINGS)
            for row in rows:
                key, val = row["key"], row["value"]
                if key in ("telegram_phone", "telegram_api_hash", "allowed_extensions", "target_channel", "verification_mode"):
                    settings[key] = str(val)
                elif str(val).lower() in ("true", "false"):
                    settings[key] = str(val).lower() == "true"
                elif str(val).isdigit():
                    settings[key] = int(val)
                else:
                    try:
                        settings[key] = float(val)
                    except ValueError:
                        settings[key] = val
            return settings

async def update_setting(key: str, value: Any):
    async with get_db_connection() as db:
        await db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def get_all_books(only_orthodox: bool = False) -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        query = "SELECT * FROM books_requested"
        if only_orthodox:
            query += " WHERE is_orthodox = 1"
        query += " ORDER BY id ASC"
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_book(
    title: str,
    author: str = "",
    isbn: str = "",
    edition: str = "",
    is_orthodox: bool = False,
    verified_by: str = "",
    verification_score: float = 0.0,
    book_category: str = "",
    verification_reason: str = "",
    source_channel_title: str = "",
    normalized_title: str = ""
) -> int:
    async with get_db_connection() as db:
        cursor = await db.execute("""
            INSERT INTO books_requested 
            (title, author, isbn, edition, status, is_orthodox, verified_by, verification_score, book_category, verification_reason, source_channel_title, normalized_title) 
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
        """, (
            title.strip(), author.strip(), isbn.strip(), edition.strip(),
            1 if is_orthodox else 0, verified_by, verification_score,
            book_category, verification_reason, source_channel_title, normalized_title
        ))
        await db.commit()
        return cursor.lastrowid

async def update_book_status(
    book_id: int,
    status: str,
    confidence: float = 0.0,
    selected_file: str = "",
    notes: str = "",
    is_orthodox: Optional[bool] = None,
    verified_by: Optional[str] = None,
    verification_score: Optional[float] = None,
    book_category: Optional[str] = None,
    verification_reason: Optional[str] = None
):
    async with get_db_connection() as db:
        updates = ["status = ?", "confidence = ?", "selected_file = ?", "notes = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status, confidence, selected_file, notes]

        if is_orthodox is not None:
            updates.append("is_orthodox = ?")
            params.append(1 if is_orthodox else 0)
        if verified_by is not None:
            updates.append("verified_by = ?")
            params.append(verified_by)
        if verification_score is not None:
            updates.append("verification_score = ?")
            params.append(verification_score)
        if book_category is not None:
            updates.append("book_category = ?")
            params.append(book_category)
        if verification_reason is not None:
            updates.append("verification_reason = ?")
            params.append(verification_reason)

        params.append(book_id)
        query = f"UPDATE books_requested SET {', '.join(updates)} WHERE id = ?"
        await db.execute(query, params)
        await db.commit()

async def delete_book(book_id: int):
    async with get_db_connection() as db:
        await db.execute("DELETE FROM books_requested WHERE id = ?", (book_id,))
        await db.commit()

async def clear_all_books():
    async with get_db_connection() as db:
        await db.execute("DELETE FROM books_requested")
        await db.commit()

async def is_file_processed(chat_id: int, message_id: int, filename: str) -> bool:
    async with get_db_connection() as db:
        async with db.execute(
            "SELECT id FROM processed_files WHERE (telegram_chat_id = ? AND telegram_message_id = ?) OR filename = ?",
            (chat_id, message_id, filename)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def record_processed_file(
    requested_title: str,
    author: str,
    source: str,
    telegram_chat_id: int,
    telegram_message_id: int,
    filename: str,
    file_size: int,
    confidence: float,
    status: str,
    file_hash: str = ""
):
    async with get_db_connection() as db:
        await db.execute("""
            INSERT INTO processed_files 
            (requested_title, author, source, telegram_chat_id, telegram_message_id, filename, file_size, file_hash, confidence, status, date_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (requested_title, author, source, telegram_chat_id, telegram_message_id, filename, file_size, file_hash, confidence, status))
        await db.commit()

async def get_processed_history(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        query = "SELECT * FROM processed_files"
        params = []
        if status_filter and status_filter.lower() != "all":
            query += " WHERE LOWER(status) = ?"
            params.append(status_filter.lower())
        query += " ORDER BY id DESC"
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def sync_sources(sources_list: List[Dict[str, Any]]):
    """Save or update discovered Telegram sources."""
    async with get_db_connection() as db:
        for s in sources_list:
            await db.execute("""
                INSERT INTO telegram_sources (chat_id, name, username, type, enabled)
                VALUES (:chat_id, :name, :username, :type, 1)
                ON CONFLICT(chat_id) DO UPDATE SET
                    name = excluded.name,
                    username = excluded.username,
                    type = excluded.type
            """, s)
        await db.commit()

async def get_all_sources() -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        async with db.execute("SELECT * FROM telegram_sources ORDER BY name ASC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def set_source_enabled(chat_id: int, enabled: bool):
    async with get_db_connection() as db:
        await db.execute("UPDATE telegram_sources SET enabled = ? WHERE chat_id = ?", (1 if enabled else 0, chat_id))
        await db.commit()

async def get_enabled_sources() -> List[Dict[str, Any]]:
    async with get_db_connection() as db:
        async with db.execute("SELECT * FROM telegram_sources WHERE enabled = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
