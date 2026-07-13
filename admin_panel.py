import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from flask import Flask, Response, flash, redirect, render_template_string, request, session, url_for
from flask_admin import Admin, AdminIndexView, expose
from flask_admin import BaseView

from storage import (
    add_bad_word,
    delete_bad_word,
    get_admin_username,
    get_message_templates,
    get_setting,
    get_required_channel,
    get_required_channel_message_limit,
    init_db,
    list_bad_words,
    parse_required_channels,
    set_setting,
    update_admin_credentials,
    verify_admin_credentials,
)


BOT_TOKEN = os.getenv("BOT_TOKEN", "")

MESSAGE_TEMPLATE_LABELS = {
    "message_welcome": {
        "label": "خوش‌آمدگویی عضو جدید",
        "hint": "متغیر قابل استفاده: {user}",
    },
    "message_required_channel": {
        "label": "هشدار عضویت اجباری در کانال",
        "hint": "متغیرهای قابل استفاده: {user} و {channel}. مقدار {channel} می‌تواند لیست چند کانال باشد.",
    },
    "message_profanity_warning": {
        "label": "هشدار حذف پیام نامناسب",
        "hint": "متغیر قابل استفاده: {user}",
    },
    "message_spam_mute": {
        "label": "هشدار میوت اسپم",
        "hint": "متغیرهای قابل استفاده: {user} و {minutes}",
    },
    "message_restrict_error": {
        "label": "خطای نداشتن دسترسی Restrict Members",
        "hint": "این پیام معمولاً فقط متن ثابت لازم دارد.",
    },
}


@dataclass
class ChannelValidationResult:
    ok: bool
    level: str
    title: str
    message: str
    detail: str = ""


def get_channel_chat_id(channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("https://t.me/"):
        path = urlparse(channel).path.strip("/")
        if path and not path.startswith("+"):
            return f"@{path.split('/')[0]}"
    return channel


def telegram_api_request(method: str, **params) -> dict:
    query = urlencode(params)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if query:
        url = f"{url}?{query}"

    try:
        with urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"ok": False, "description": body or str(exc)}
    except URLError as exc:
        return {"ok": False, "description": f"خطای شبکه: {exc.reason}"}
    except TimeoutError:
        return {"ok": False, "description": "درخواست به تلگرام زمان‌بر شد و timeout خورد."}
    except json.JSONDecodeError:
        return {"ok": False, "description": "پاسخ تلگرام قابل خواندن نبود."}

    return payload


def validate_required_channel(channel: str) -> ChannelValidationResult:
    channel = channel.strip()
    if not channel:
        return ChannelValidationResult(
            ok=True,
            level="info",
            title="قانون کانال غیرفعال است",
            message="کانالی وارد نشده؛ عضویت اجباری فعلاً اعمال نمی‌شود.",
        )
    if not BOT_TOKEN:
        return ChannelValidationResult(
            ok=False,
            level="danger",
            title="توکن بات تنظیم نشده",
            message="برای چک کانال، متغیر BOT_TOKEN باید برای سرویس پنل هم تنظیم باشد.",
        )

    chat_id = get_channel_chat_id(channel)
    bot_response = telegram_api_request("getMe")
    if not bot_response.get("ok"):
        return ChannelValidationResult(
            ok=False,
            level="danger",
            title="توکن بات معتبر نیست",
            message="پنل نتوانست اطلاعات ربات را از تلگرام دریافت کند.",
            detail=bot_response.get("description", ""),
        )

    bot_user_id = bot_response["result"]["id"]
    chat_response = telegram_api_request("getChat", chat_id=chat_id)
    if not chat_response.get("ok"):
        return ChannelValidationResult(
            ok=False,
            level="danger",
            title="کانال پیدا نشد یا در دسترس نیست",
            message=(
                "شناسه/یوزرنیم کانال را بررسی کنید. برای کانال خصوصی معمولاً باید "
                "شناسه عددی کانال را وارد کنید و ربات داخل کانال باشد."
            ),
            detail=chat_response.get("description", ""),
        )

    member_response = telegram_api_request(
        "getChatMember",
        chat_id=chat_id,
        user_id=bot_user_id,
    )
    if not member_response.get("ok"):
        return ChannelValidationResult(
            ok=False,
            level="danger",
            title="ربات هنوز داخل کانال قابل بررسی نیست",
            message="ربات را به کانال اضافه و ادمین کنید، سپس دوباره دکمه ذخیره را بزنید.",
            detail=member_response.get("description", ""),
        )

    chat = chat_response["result"]
    member = member_response["result"]
    status = member.get("status", "")
    chat_title = chat.get("title") or chat.get("username") or chat_id
    if status not in {"administrator", "creator"}:
        return ChannelValidationResult(
            ok=False,
            level="warning",
            title="ربات هنوز ادمین کانال نیست",
            message=(
                f"کانال «{chat_title}» پیدا شد، اما وضعیت ربات «{status or 'نامشخص'}» است. "
                "ربات را در کانال ادمین کنید و دوباره ذخیره/بررسی را بزنید."
            ),
        )

    return ChannelValidationResult(
        ok=True,
        level="success",
        title="ربات ادمین کانال است",
        message=f"کانال «{chat_title}» بررسی شد؛ ربات ادمین است و همه چیز اوکیه.",
    )


def validate_required_channels(raw_channels: str) -> list[ChannelValidationResult]:
    channels = parse_required_channels(raw_channels)
    if not channels:
        return [validate_required_channel("")]
    return [validate_required_channel(channel) for channel in channels]


BASE_CSS = """
<style>
  :root {
    --ink: #111827;
    --muted: #64748b;
    --line: #d8e0ea;
    --bg: #f5f7fb;
    --panel: #ffffff;
    --panel-soft: #f8fafc;
    --accent: #0f766e;
    --accent-dark: #134e4a;
    --accent-soft: #e6f4f1;
    --danger: #dc2626;
    --danger-soft: #fef2f2;
    --shadow: 0 18px 45px rgba(15, 23, 42, .08);
  }
  * {
    box-sizing: border-box;
  }
  body {
    min-height: 100vh;
    background: linear-gradient(180deg, #ffffff 0%, var(--bg) 100%);
    color: var(--ink);
    font-family: Vazirmatn, Tahoma, Arial, sans-serif;
    font-size: 15px;
  }
  .navbar, .navbar-default {
    background: rgba(255,255,255,.96) !important;
    border: 0;
    border-bottom: 1px solid var(--line);
    box-shadow: 0 10px 30px rgba(15, 23, 42, .06);
    direction: rtl;
  }
  .navbar-header {
    float: right;
  }
  .navbar-nav {
    float: right;
    padding-right: 0;
  }
  .navbar-nav > li {
    float: right;
  }
  .navbar-toggle {
    float: left;
    margin-left: 15px;
    margin-right: 0;
  }
  .navbar-brand, .nav-link, .navbar-nav > li > a {
    color: var(--ink) !important;
    font-weight: 800;
  }
  .navbar-brand {
    letter-spacing: 0;
  }
  .navbar-nav > li > a {
    border-radius: 8px;
    margin: 8px 2px;
    padding: 9px 12px !important;
  }
  .navbar-nav > li.active > a,
  .navbar-nav > li > a:hover,
  .navbar-nav > li > a:focus {
    background: var(--accent-soft) !important;
    color: var(--accent-dark) !important;
  }
  .container, .container-fluid {
    max-width: 1120px;
    width: min(1120px, calc(100% - 32px));
    padding-left: 0;
    padding-right: 0;
  }
  .admin-shell {
    direction: rtl;
    padding: 30px 0 48px;
  }
  .hero {
    display: grid;
    gap: 8px;
    margin-bottom: 20px;
  }
  .hero h1 {
    margin: 0;
    font-size: 34px;
    line-height: 1.35;
    font-weight: 900;
    letter-spacing: 0;
  }
  .hero p {
    margin: 0;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.9;
    max-width: 760px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }
  .panel-card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 18px;
    box-shadow: var(--shadow);
  }
  .panel-card h2, .panel-card h3 {
    margin: 0 0 12px;
    font-size: 18px;
    font-weight: 900;
  }
  .panel-card p:last-child {
    margin-bottom: 0;
  }
  .card-actions {
    margin-top: 16px;
  }
  .metric {
    font-size: 38px;
    line-height: 1;
    font-weight: 900;
    color: var(--accent-dark);
    margin-bottom: 10px;
  }
  .muted {
    color: var(--muted);
    line-height: 1.8;
  }
  .admin-form {
    display: grid;
    gap: 10px;
  }
  .admin-form label {
    font-weight: 800;
    margin: 0;
  }
  .admin-form input,
  .admin-form textarea {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 9px 12px;
    background: #fff;
    color: var(--ink);
    box-shadow: inset 0 1px 2px rgba(15, 23, 42, .03);
  }
  .admin-form input {
    min-height: 46px;
  }
  .admin-form textarea {
    min-height: 140px;
    resize: vertical;
    line-height: 1.9;
    direction: rtl;
  }
  .admin-form input:focus,
  .admin-form textarea:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(15, 118, 110, .14);
    outline: 0;
  }
  .actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
  }
  .btn-primary, .pretty-btn {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    color: #fff !important;
    border-radius: 8px;
    border-style: solid;
    border-width: 1px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    font-weight: 800;
    padding: 10px 16px;
    text-align: center;
    white-space: nowrap;
  }
  .pretty-btn:hover {
    background: var(--accent-dark) !important;
    text-decoration: none;
  }
  .danger-btn {
    background: var(--danger-soft);
    color: var(--danger);
    border: 1px solid rgba(220, 38, 38, .20);
    border-radius: 8px;
    min-height: 38px;
    padding: 8px 12px;
    font-weight: 800;
  }
  .danger-btn:hover {
    background: #fee2e2;
  }
  .word-list {
    display: grid;
    gap: 8px;
    margin-top: 16px;
  }
  .word-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px 12px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, .04);
  }
  .word {
    font-weight: 900;
    overflow-wrap: anywhere;
    min-width: 0;
  }
  .badge-soft {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    max-width: 100%;
    background: rgba(15, 118, 110, .10);
    color: var(--accent-dark);
    border: 1px solid rgba(15, 118, 110, .20);
    border-radius: 999px;
    padding: 5px 10px;
    font-weight: 800;
    overflow-wrap: anywhere;
  }
  .alert {
    direction: rtl;
    border-radius: 8px;
  }
  .status-card {
    border-radius: 8px;
    padding: 14px;
    border: 1px solid var(--line);
    margin-bottom: 14px;
  }
  .status-success {
    background: #ecfdf5;
    border-color: #a7f3d0;
    color: #065f46;
  }
  .status-warning {
    background: #fffbeb;
    border-color: #fde68a;
    color: #92400e;
  }
  .status-danger {
    background: #fef2f2;
    border-color: #fecaca;
    color: #991b1b;
  }
  .status-info {
    background: #eff6ff;
    border-color: #bfdbfe;
    color: #1e40af;
  }
  .status-card h3 {
    margin: 0 0 6px;
    font-size: 16px;
    font-weight: 900;
  }
  .status-list {
    display: grid;
    gap: 10px;
    margin-bottom: 14px;
  }
  .channel-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 12px 0 0;
  }
  .channel-chip {
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 6px 10px;
    color: var(--ink);
    font-weight: 800;
    overflow-wrap: anywhere;
  }
  .template-grid {
    display: grid;
    gap: 14px;
  }
  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
  }
  .switch {
    position: relative;
    display: inline-block;
    width: 56px;
    height: 32px;
    flex: 0 0 auto;
  }
  .switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }
  .slider {
    position: absolute;
    cursor: pointer;
    inset: 0;
    background: #cbd5e1;
    border-radius: 999px;
    transition: .2s;
  }
  .slider:before {
    position: absolute;
    content: "";
    height: 24px;
    width: 24px;
    left: 4px;
    bottom: 4px;
    background: #fff;
    border-radius: 50%;
    box-shadow: 0 2px 8px rgba(15, 23, 42, .22);
    transition: .2s;
  }
  .switch input:checked + .slider {
    background: var(--accent);
  }
  .switch input:checked + .slider:before {
    transform: translateX(24px);
  }
  .ltr {
    direction: ltr;
    text-align: left;
  }
  .login-shell {
    max-width: 460px;
    margin: 0 auto;
    min-height: 100vh;
    display: grid;
    align-content: center;
    padding: 24px 0;
  }
  @media (max-width: 900px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
  @media (max-width: 767px) {
    body {
      font-size: 14px;
    }
    .container, .container-fluid {
      width: min(100% - 24px, 1120px);
    }
    .navbar-header {
      float: none;
    }
    .navbar-nav,
    .navbar-nav > li {
      float: none;
    }
    .navbar-nav {
      margin: 8px 0;
    }
    .navbar-nav > li > a {
      margin: 4px 0;
      padding: 11px 12px !important;
    }
    .admin-shell {
      padding: 22px 0 34px;
    }
    .hero h1 {
      font-size: 26px;
    }
    .panel-card {
      padding: 15px;
    }
    .actions {
      display: grid;
      grid-template-columns: 1fr;
    }
    .pretty-btn,
    .btn-primary {
      width: 100%;
    }
    .word-row {
      align-items: stretch;
      flex-direction: column;
    }
    .word-row form,
    .word-row .danger-btn {
      width: 100%;
    }
    .login-shell {
      align-content: start;
      padding-top: 34px;
    }
  }
</style>
"""


def create_app() -> Flask:
    init_db()
    app = Flask(__name__)
    app.secret_key = os.getenv("ADMIN_SECRET_KEY", "change-me-admin-secret")

    @app.before_request
    def require_login() -> Response | None:
        public_endpoints = {"login", "static"}
        if request.endpoint in public_endpoints:
            return None
        if session.get("admin_logged_in"):
            return None
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> str | Response:
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if verify_admin_credentials(username, password):
                session["admin_logged_in"] = True
                return redirect(url_for("admin.index"))
            flash("نام کاربری یا رمز عبور اشتباه است.", "danger")

        return render_template_string(
            BASE_CSS
            + """
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <main class="admin-shell login-shell">
              <section class="hero">
                <span class="badge-soft">پنل مدیریت بات تلگرام</span>
                <h1>ورود مدیر</h1>
                <p>برای مدیریت کلمات ممنوعه و کانال اجباری وارد شوید.</p>
              </section>
              {% with messages = get_flashed_messages(with_categories=true) %}
                {% for category, message in messages %}
                  <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
              {% endwith %}
              <section class="panel-card">
                <form class="admin-form" method="post">
                  <label>نام کاربری</label>
                  <input name="username" autocomplete="username" required autofocus>
                  <label>رمز عبور</label>
                  <input name="password" type="password" autocomplete="current-password" required>
                  <button class="pretty-btn" type="submit">ورود به پنل</button>
                </form>
              </section>
            </main>
            """
        )

    @app.route("/logout")
    def logout() -> Response:
        session.clear()
        return redirect(url_for("login"))

    admin = Admin(
        app,
        name="پنل مدیریت بات",
        index_view=DashboardView(url="/admin"),
    )
    admin.add_view(BadWordsView(name="کلمات ممنوعه", endpoint="bad_words"))
    admin.add_view(SettingsView(name="تنظیمات کانال", endpoint="settings"))
    admin.add_view(MessagesView(name="پیام‌های ربات", endpoint="messages"))
    admin.add_view(AdminSettingsView(name="تنظیمات ادمین", endpoint="admin_settings"))
    return app


class DashboardView(AdminIndexView):
    @expose("/")
    def index(self) -> str:
        words = list_bad_words()
        channel = get_required_channel()
        limit = get_required_channel_message_limit()
        return self.render(
            "admin/dashboard.html",
            base_css=BASE_CSS,
            words_count=len(words),
            channel=channel,
            channels=parse_required_channels(channel),
            limit=limit,
        )


class BadWordsView(BaseView):
    @expose("/", methods=["GET", "POST"])
    def index(self) -> str | Response:
        if request.method == "POST":
            add_bad_word(request.form.get("word", ""))
            flash("کلمه ممنوعه ذخیره شد.", "success")
            return redirect(url_for(".index"))

        return self.render(
            "admin/bad_words.html",
            base_css=BASE_CSS,
            words=list_bad_words(),
        )

    @expose("/delete/<int:word_id>", methods=["POST"])
    def delete(self, word_id: int) -> Response:
        delete_bad_word(word_id)
        flash("کلمه حذف شد.", "success")
        return redirect(url_for(".index"))


class SettingsView(BaseView):
    @expose("/", methods=["GET", "POST"])
    def index(self) -> str | Response:
        validations = [
            ChannelValidationResult(
                ok=True,
                level="info",
                title="آماده بررسی کانال‌ها",
                message="بعد از وارد کردن کانال‌ها و ذخیره، پنل وضعیت ادمین بودن ربات را برای تک‌تک کانال‌ها بررسی می‌کند.",
            )
        ]
        if request.method == "POST":
            channel = "\n".join(
                parse_required_channels(request.form.get("required_channel", ""))
            )
            set_setting(
                "required_channel_message_limit",
                request.form.get("required_channel_message_limit", "5"),
            )
            set_setting("required_channel", channel)
            validations = validate_required_channels(channel)
            if all(result.ok for result in validations):
                flash("همه کانال‌ها بررسی شدند و همه چیز اوکیه.", "success")
            else:
                flash("بعضی کانال‌ها نیاز به بررسی دارند؛ وضعیت هر کانال پایین نمایش داده شده.", "warning")

        return self.render(
            "admin/settings.html",
            base_css=BASE_CSS,
            channel=get_required_channel(),
            channels=parse_required_channels(get_required_channel()),
            limit=get_required_channel_message_limit(),
            validations=validations,
        )


class MessagesView(BaseView):
    @expose("/", methods=["GET", "POST"])
    def index(self) -> str | Response:
        if request.method == "POST":
            set_setting("welcome_enabled", "1" if request.form.get("welcome_enabled") else "0")
            for key in MESSAGE_TEMPLATE_LABELS:
                set_setting(key, request.form.get(key, ""))
            flash("پیام‌های ربات ذخیره شد.", "success")
            return redirect(url_for(".index"))

        return self.render(
            "admin/messages.html",
            base_css=BASE_CSS,
            labels=MESSAGE_TEMPLATE_LABELS,
            templates=get_message_templates(),
            welcome_enabled=get_setting("welcome_enabled", "1") == "1",
        )


class AdminSettingsView(BaseView):
    @expose("/", methods=["GET", "POST"])
    def index(self) -> str | Response:
        if request.method == "POST":
            username = request.form.get("admin_username", "")
            password = request.form.get("admin_password", "")
            password_confirm = request.form.get("admin_password_confirm", "")

            if not username.strip():
                flash("نام کاربری نمی‌تواند خالی باشد.", "danger")
            elif password and password != password_confirm:
                flash("تکرار رمز عبور با رمز جدید یکی نیست.", "danger")
            else:
                try:
                    update_admin_credentials(username, password or None)
                except ValueError:
                    flash("نام کاربری نمی‌تواند خالی باشد.", "danger")
                else:
                    session["admin_logged_in"] = True
                    flash("تنظیمات ادمین ذخیره شد.", "success")
                    return redirect(url_for(".index"))

        return self.render(
            "admin/admin_settings.html",
            base_css=BASE_CSS,
            admin_username=get_admin_username(),
        )


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("ADMIN_PORT", "5000")))
