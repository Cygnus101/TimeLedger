import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from utils import date_to_text, generate_time_slots


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "time_ledger.db"

DEFAULT_CATEGORIES = [
    ("Research_Work", "#15803d", 1),
    ("Study", "#22c55e", 1),
    ("Personal_Projects", "#86efac", 1),
    ("Sleep", "#7f1d1d", 0),
    ("Workout", "#1d4ed8", 1),
    ("Meals", "#7e22ce", 0),
    ("Hygiene", "#06b6d4", 0),
    ("Travel", "#a855f7", 0),
    ("Game", "#dc2626", 0),
    ("Drawing", "#3b82f6", 1),
    ("Reading", "#93c5fd", 1),
    ("Misc", "#fca5a5", 0),
]


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS time_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                slot_index INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                category TEXT,
                note TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(date, slot_index)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT,
                is_productive INTEGER DEFAULT 0
            )
            """
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO categories (name, color, is_productive)
            VALUES (?, ?, ?)
            """,
            DEFAULT_CATEGORIES,
        )
        conn.executemany(
            """
            UPDATE categories
            SET color = ?, is_productive = ?
            WHERE name = ?
            """,
            [(color, is_productive, name) for name, color, is_productive in DEFAULT_CATEGORIES],
        )


def get_categories() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM categories ORDER BY id").fetchall()
    return [row["name"] for row in rows]


def get_category_colors() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT name, COALESCE(color, '#000000') AS color
            FROM categories
            ORDER BY id
            """
        ).fetchall()

    return {row["name"]: row["color"] for row in rows}


def ensure_day_records(day) -> None:
    day_text = date_to_text(day)
    now = datetime.now().isoformat(timespec="seconds")
    rows = [
        (
            day_text,
            slot["slot_index"],
            slot["start_time"],
            slot["end_time"],
            now,
            now,
        )
        for slot in generate_time_slots()
    ]

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO time_blocks
                (date, slot_index, start_time, end_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def get_day_blocks(day) -> pd.DataFrame:
    ensure_day_records(day)
    day_text = date_to_text(day)

    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                date,
                slot_index,
                start_time,
                end_time,
                COALESCE(category, '') AS category,
                COALESCE(note, '') AS note
            FROM time_blocks
            WHERE date = ?
            ORDER BY slot_index
            """,
            conn,
            params=(day_text,),
        )

    df["Time"] = df["start_time"] + " - " + df["end_time"]
    df["Category"] = df["category"]
    df["Note"] = df["note"]
    return df


def update_day_blocks(day, edited_df: pd.DataFrame) -> None:
    day_text = date_to_text(day)
    now = datetime.now().isoformat(timespec="seconds")
    rows = []

    for record in edited_df.to_dict("records"):
        category = clean_optional_value(record.get("Category"))
        note = clean_optional_value(record.get("Note"))
        rows.append((category, note, now, day_text, int(record["slot_index"])))

    with get_connection() as conn:
        conn.executemany(
            """
            UPDATE time_blocks
            SET category = ?, note = ?, updated_at = ?
            WHERE date = ? AND slot_index = ?
            """,
            rows,
        )


def fill_time_range(day, start_slot: int, end_slot: int, category: str, note: str) -> None:
    ensure_day_records(day)
    day_text = date_to_text(day)
    now = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE time_blocks
            SET category = ?, note = ?, updated_at = ?
            WHERE date = ?
              AND slot_index >= ?
              AND slot_index < ?
            """,
            (clean_optional_value(category), clean_optional_value(note), now, day_text, start_slot, end_slot),
        )


def get_blocks_for_dates(days: list) -> pd.DataFrame:
    for day in days:
        ensure_day_records(day)

    date_values = [date_to_text(day) for day in days]
    placeholders = ",".join("?" for _ in date_values)

    with get_connection() as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                date,
                slot_index,
                start_time,
                end_time,
                COALESCE(category, '') AS category,
                COALESCE(note, '') AS note
            FROM time_blocks
            WHERE date IN ({placeholders})
            ORDER BY date, slot_index
            """,
            conn,
            params=date_values,
        )


def get_month_activity(year: int, month: int) -> dict[str, bool]:
    month_prefix = f"{year:04d}-{month:02d}"

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT date
            FROM time_blocks
            WHERE substr(date, 1, 7) = ?
              AND (
                  COALESCE(TRIM(category), '') != ''
                  OR COALESCE(TRIM(note), '') != ''
              )
            GROUP BY date
            """,
            (month_prefix,),
        ).fetchall()

    return {row["date"]: True for row in rows}


def get_month_day_colors(year: int, month: int) -> dict[str, str]:
    month_prefix = f"{year:04d}-{month:02d}"

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                tb.date,
                tb.category,
                COALESCE(c.color, '#000000') AS color,
                COUNT(*) AS block_count
            FROM time_blocks tb
            LEFT JOIN categories c ON c.name = tb.category
            WHERE substr(tb.date, 1, 7) = ?
              AND COALESCE(TRIM(tb.category), '') != ''
            GROUP BY tb.date, tb.category, c.color
            ORDER BY tb.date, block_count DESC, tb.category
            """,
            (month_prefix,),
        ).fetchall()

    day_colors = {}
    for row in rows:
        day_colors.setdefault(row["date"], row["color"])

    return day_colors


def clean_optional_value(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None
