import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram import ChatPermissions, Update
from telegram.constants import ChatType
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application, ContextTypes, MessageHandler, filters


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BAD_WORDS_FILE = Path("bad_words.txt")
SPAM_WINDOW_SECONDS = 8
SPAM_MAX_MESSAGES = 5
SPAM_REPEAT_WINDOW_SECONDS = 20
SPAM_REPEAT_MAX = 3
SPAM_MUTE_SECONDS = 10 * 60

# In-memory anti-spam tracking (resets on bot restart).
MESSAGE_TIMES: dict[tuple[int, int], deque[float]] = defaultdict(deque)
REPEAT_STATE: dict[tuple[int, int], tuple[str, int, float]] = {}


def normalize_text(text: str) -> str:
    # Normalize to lower case and strip zero-width chars commonly used to bypass filters.
    return (
        text.lower()
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
        .strip()
    )


def load_bad_words(file_path: Path) -> list[str]:
    if not file_path.exists():
        logger.warning("bad_words.txt not found. Starting with empty profanity list.")
        return []

    words: list[str] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words.append(normalize_text(line))
    return sorted(set(words))


BAD_WORDS = load_bad_words(BAD_WORDS_FILE)


def contains_bad_word(text: str) -> bool:
    if not BAD_WORDS:
        return False
    clean_text = normalize_text(text)
    return any(word in clean_text for word in BAD_WORDS)


def detect_spam(chat_id: int, user_id: int, text: str) -> bool:
    key = (chat_id, user_id)
    now = time.monotonic()

    # Rule 1: too many messages in a short window.
    times = MESSAGE_TIMES[key]
    times.append(now)
    while times and (now - times[0]) > SPAM_WINDOW_SECONDS:
        times.popleft()
    if len(times) > SPAM_MAX_MESSAGES:
        return True

    # Rule 2: repeated same text in a short window.
    clean_text = normalize_text(text)
    if clean_text:
        previous = REPEAT_STATE.get(key)
        if previous:
            prev_text, prev_count, prev_at = previous
            if clean_text == prev_text and (now - prev_at) <= SPAM_REPEAT_WINDOW_SECONDS:
                REPEAT_STATE[key] = (clean_text, prev_count + 1, now)
            else:
                REPEAT_STATE[key] = (clean_text, 1, now)
        else:
            REPEAT_STATE[key] = (clean_text, 1, now)

        _, repeat_count, _ = REPEAT_STATE[key]
        if repeat_count >= SPAM_REPEAT_MAX:
            return True

    return False


async def is_user_admin(
    chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramError as exc:
        logger.warning("Could not read chat member status: %s", exc)
        return False
    return member.status in {"administrator", "creator"}


async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.new_chat_members:
        return

    chat = update.effective_chat
    if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    for member in update.message.new_chat_members:
        await update.message.reply_text(
            f"خوش اومدی {member.mention_html()} 🌟\n"
            "قوانین گروه رو لطفاً رعایت کن.",
            parse_mode="HTML",
        )


async def moderate_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if await is_user_admin(chat_id=chat.id, user_id=user.id, context=context):
        # Admins/owners are fully exempt from moderation rules.
        return

    text = update.message.text or update.message.caption or ""
    if text and contains_bad_word(text):
        try:
            await update.message.delete()
        except TelegramError as exc:
            logger.warning("Could not delete message: %s", exc)

        try:
            await context.bot.ban_chat_member(chat_id=chat.id, user_id=user.id)
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"کاربر {user.mention_html()} به دلیل توهین بن شد.",
                parse_mode="HTML",
            )
        except Forbidden:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "نتونستم بن کنم. ربات باید ادمین باشه و مجوز Ban Users داشته باشه."
                ),
            )
        except TelegramError as exc:
            logger.error("Ban failed: %s", exc)
        return

    if not detect_spam(chat_id=chat.id, user_id=user.id, text=text):
        return

    try:
        await update.message.delete()
    except TelegramError as exc:
        logger.warning("Could not delete spam message: %s", exc)

    try:
        until_date = datetime.now(timezone.utc) + timedelta(seconds=SPAM_MUTE_SECONDS)
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"کاربر {user.mention_html()} به دلیل اسپم "
                f"به مدت {SPAM_MUTE_SECONDS // 60} دقیقه میوت شد."
            ),
            parse_mode="HTML",
        )
    except Forbidden:
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                "نتونستم میوت کنم. ربات باید ادمین باشه و مجوز Restrict Members داشته باشه."
            ),
        )
    except TelegramError as exc:
        logger.error("Mute failed: %s", exc)


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Export BOT_TOKEN and run again.")

    application = Application.builder().token(token).build()

    application.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members)
    )
    application.add_handler(
        MessageHandler(filters.TEXT | filters.CAPTION, moderate_messages)
    )

    logger.info("Bot started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
