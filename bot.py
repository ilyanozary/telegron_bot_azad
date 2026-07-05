import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlparse

from telegram import ChatPermissions, Update
from telegram.constants import ChatType
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application, ChatMemberHandler, ContextTypes, MessageHandler, filters

from storage import (
    get_bad_words,
    get_required_channel,
    get_required_channel_message_limit,
    init_db,
    normalize_text,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SPAM_WINDOW_SECONDS = 8
SPAM_MAX_MESSAGES = 15
SPAM_REPEAT_WINDOW_SECONDS = 20
SPAM_REPEAT_MAX = 8
SPAM_MUTE_SECONDS = 10 * 60

# In-memory anti-spam tracking (resets on bot restart).
MESSAGE_TIMES: dict[tuple[int, int], deque[float]] = defaultdict(deque)
REPEAT_STATE: dict[tuple[int, int], tuple[str, int, float]] = {}
CHANNEL_JOIN_MESSAGE_COUNTS: dict[tuple[int, int, str], int] = defaultdict(int)


def describe_chat(chat) -> str:
    title = getattr(chat, "title", None) or getattr(chat, "full_name", None) or "بدون عنوان"
    username = getattr(chat, "username", None)
    username_text = f"@{username}" if username else "بدون username"
    return f"title={title!r}, username={username_text}, id={chat.id}, type={chat.type}"


def describe_admin_permissions(member) -> str:
    permission_names = (
        "can_delete_messages",
        "can_restrict_members",
        "can_invite_users",
        "can_manage_chat",
        "can_post_messages",
        "can_edit_messages",
    )
    enabled = [name for name in permission_names if getattr(member, name, False)]
    return ", ".join(enabled) if enabled else "بدون دسترسی ادمین"


def is_admin_status(status: str) -> bool:
    return status in {"administrator", "creator"}


def contains_bad_word(text: str) -> bool:
    bad_words = get_bad_words()
    if not bad_words:
        return False
    clean_text = normalize_text(text)
    return any(word in clean_text for word in bad_words)


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


def get_channel_chat_id(channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("https://t.me/"):
        path = urlparse(channel).path.strip("/")
        if path and not path.startswith("+"):
            return f"@{path.split('/')[0]}"
    return channel


def get_channel_join_link(channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("http://") or channel.startswith("https://"):
        return channel
    if channel.startswith("@"):
        return f"https://t.me/{channel[1:]}"
    return channel


async def get_channel_join_text(
    channel: str, context: ContextTypes.DEFAULT_TYPE
) -> str:
    channel = channel.strip()
    chat_id = get_channel_chat_id(channel)

    if channel.startswith("http://") or channel.startswith("@"):
        return get_channel_join_link(channel)

    try:
        chat = await context.bot.get_chat(chat_id=chat_id)
    except TelegramError as exc:
        logger.warning(
            "Could not resolve required channel display text. channel=%r chat_id=%r error=%s",
            channel,
            chat_id,
            exc,
        )
        return "کانال تعیین‌شده"

    if chat.username:
        return f"https://t.me/{chat.username}"

    if chat.title:
        return escape(chat.title)

    return "کانال تعیین‌شده"


async def is_user_required_channel_member(
    channel: str, user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> bool | None:
    chat_id = get_channel_chat_id(channel)
    if not chat_id:
        return True

    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramError as exc:
        logger.warning(
            "Could not check required channel membership. channel=%r chat_id=%r user_id=%s error=%s",
            channel,
            chat_id,
            user_id,
            exc,
        )
        return None

    return member.status in {"administrator", "creator", "member"}


async def log_required_channel_access(application: Application) -> None:
    channel = get_required_channel()
    if not channel:
        logger.info("Required channel is not configured.")
        return

    chat_id = get_channel_chat_id(channel)
    bot = application.bot
    try:
        bot_user = await bot.get_me()
        chat = await bot.get_chat(chat_id=chat_id)
        member = await bot.get_chat_member(chat_id=chat_id, user_id=bot_user.id)
    except TelegramError as exc:
        logger.warning(
            "Could not read bot access for required channel. channel=%r chat_id=%r error=%s",
            channel,
            chat_id,
            exc,
        )
        return

    logger.info(
        "Required channel access: %s, bot_status=%s, bot_is_admin=%s, permissions=%s",
        describe_chat(chat),
        member.status,
        is_admin_status(member.status),
        describe_admin_permissions(member),
    )


async def log_bot_chat_member_update(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    change = update.my_chat_member
    if not change:
        return

    chat = change.chat
    old_member = change.old_chat_member
    new_member = change.new_chat_member
    logger.info(
        "Bot membership changed: %s, old_status=%s, new_status=%s, bot_is_admin=%s, permissions=%s",
        describe_chat(chat),
        old_member.status,
        new_member.status,
        is_admin_status(new_member.status),
        describe_admin_permissions(new_member),
    )


async def enforce_required_channel_membership(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    channel = get_required_channel()
    if not chat or not user or not message or not channel:
        return False

    is_member = await is_user_required_channel_member(channel, user.id, context)
    if is_member is True:
        CHANNEL_JOIN_MESSAGE_COUNTS.pop((chat.id, user.id, channel), None)
        return False
    if is_member is None:
        return False

    key = (chat.id, user.id, channel)
    CHANNEL_JOIN_MESSAGE_COUNTS[key] += 1
    message_limit = get_required_channel_message_limit()
    if CHANNEL_JOIN_MESSAGE_COUNTS[key] < message_limit:
        return False

    try:
        await message.delete()
    except TelegramError as exc:
        logger.warning("Could not delete non-member message: %s", exc)

    channel_text = await get_channel_join_text(channel, context)
    await context.bot.send_message(
        chat_id=chat.id,
        text=(
            f"{user.mention_html()} عزیز،\n\n"
            "برای ادامه فعالیت در گروه، لطفاً ابتدا در کانال زیر عضو شوید:\n"
            f"{channel_text}\n\n"
            "پس از عضویت، می‌توانید پیام خود را دوباره ارسال کنید."
        ),
        parse_mode="HTML",
    )
    return True


async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.new_chat_members:
        return

    chat = update.effective_chat
    if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    for member in update.message.new_chat_members:
        await update.message.reply_text(
            f"{member.mention_html()} عزیز، به گروه خوش آمدید.\n\n"
            "لطفاً قوانین گروه را رعایت کنید و از ارسال پیام‌های نامرتبط یا تکراری خودداری فرمایید.",
            parse_mode="HTML",
        )


async def moderate_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if update.message.new_chat_members:
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
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"{user.mention_html()} عزیز،\n\n"
                    "پیام شما به دلیل استفاده از عبارت نامناسب حذف شد. "
                    "لطفاً در ادامه گفتگو، قوانین گروه را رعایت فرمایید."
                ),
                parse_mode="HTML",
            )
        except TelegramError as exc:
            logger.error("Could not send profanity warning: %s", exc)
        return

    if await enforce_required_channel_membership(update, context):
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
                f"{user.mention_html()} عزیز،\n\n"
                "به دلیل ارسال پیام‌های متعدد یا تکراری، دسترسی ارسال پیام شما "
                f"به مدت {SPAM_MUTE_SECONDS // 60} دقیقه محدود شد.\n\n"
                "پس از پایان محدودیت، لطفاً پیام‌ها را با فاصله و بدون تکرار ارسال فرمایید."
            ),
            parse_mode="HTML",
        )
    except Forbidden:
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                "امکان اعمال محدودیت وجود ندارد. لطفاً دسترسی ادمین ربات و مجوز "
                "Restrict Members را بررسی کنید."
            ),
        )
    except TelegramError as exc:
        logger.error("Mute failed: %s", exc)


def main() -> None:
    init_db()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Export BOT_TOKEN and run again.")

    application = Application.builder().token(token).post_init(log_required_channel_access).build()

    application.add_handler(ChatMemberHandler(log_bot_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members)
    )
    application.add_handler(MessageHandler(filters.ALL, moderate_messages))

    logger.info("Bot started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
