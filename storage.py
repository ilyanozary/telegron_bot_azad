import os
import sqlite3
from pathlib import Path


DB_PATH = Path(os.getenv("BOT_DB_PATH", "bot_settings.sqlite3"))
BAD_WORDS_FILE = Path("bad_words.txt")

DEFAULT_SETTINGS = {
    "required_channel": "",
    "required_channel_message_limit": "5",
    "message_welcome": (
        "{user} عزیز، به گروه خوش آمدید.\n\n"
        "لطفاً قوانین گروه را رعایت کنید و از ارسال پیام‌های نامرتبط یا تکراری خودداری فرمایید."
    ),
    "message_required_channel": (
        "{user} عزیز،\n\n"
        "برای ادامه فعالیت در گروه، لطفاً ابتدا در کانال زیر عضو شوید:\n"
        "{channel}\n\n"
        "پس از عضویت، می‌توانید پیام خود را دوباره ارسال کنید."
    ),
    "message_profanity_warning": (
        "{user} عزیز،\n\n"
        "پیام شما به دلیل استفاده از عبارت نامناسب حذف شد. "
        "لطفاً در ادامه گفتگو، قوانین گروه را رعایت فرمایید."
    ),
    "message_spam_mute": (
        "{user} عزیز،\n\n"
        "به دلیل ارسال پیام‌های متعدد یا تکراری، دسترسی ارسال پیام شما "
        "به مدت {minutes} دقیقه محدود شد.\n\n"
        "پس از پایان محدودیت، لطفاً پیام‌ها را با فاصله و بدون تکرار ارسال فرمایید."
    ),
    "message_restrict_error": (
        "امکان اعمال محدودیت وجود ندارد. لطفاً دسترسی ادمین ربات و مجوز "
        "Restrict Members را بررسی کنید."
    ),
}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bad_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        for key, value in DEFAULT_SETTINGS.items():
            connection.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

        bad_words_count = connection.execute(
            "SELECT COUNT(*) FROM bad_words"
        ).fetchone()[0]
        if bad_words_count == 0:
            import_bad_words_file(connection)


def normalize_text(text: str) -> str:
    return (
        text.lower()
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
        .strip()
    )


def import_bad_words_file(connection: sqlite3.Connection) -> None:
    if not BAD_WORDS_FILE.exists():
        return

    for line in BAD_WORDS_FILE.read_text(encoding="utf-8").splitlines():
        word = normalize_text(line)
        if not word or word.startswith("#"):
            continue
        connection.execute(
            "INSERT OR IGNORE INTO bad_words (word) VALUES (?)",
            (word,),
        )


def get_bad_words() -> list[str]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT word FROM bad_words ORDER BY word COLLATE NOCASE"
        ).fetchall()
    return [row["word"] for row in rows]


def add_bad_word(word: str) -> None:
    clean_word = normalize_text(word)
    if not clean_word:
        return
    init_db()
    with get_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO bad_words (word) VALUES (?)",
            (clean_word,),
        )


def delete_bad_word(word_id: int) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute("DELETE FROM bad_words WHERE id = ?", (word_id,))


def list_bad_words() -> list[sqlite3.Row]:
    init_db()
    with get_connection() as connection:
        return connection.execute(
            "SELECT id, word, created_at FROM bad_words ORDER BY word COLLATE NOCASE"
        ).fetchall()


def get_setting(key: str, default: str = "") -> str:
    init_db()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value.strip()),
        )


def get_required_channel() -> str:
    return get_setting("required_channel")


def get_required_channel_message_limit() -> int:
    raw_limit = get_setting("required_channel_message_limit", "5")
    try:
        return max(1, int(raw_limit))
    except ValueError:
        return 5


def get_message_template(key: str) -> str:
    return get_setting(key, DEFAULT_SETTINGS.get(key, ""))


def get_message_templates() -> dict[str, str]:
    init_db()
    return {
        key: get_setting(key, value)
        for key, value in DEFAULT_SETTINGS.items()
        if key.startswith("message_")
    }
