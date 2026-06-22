import os

from flask import Flask, Response, flash, redirect, render_template_string, request, session, url_for
from flask_admin import Admin, AdminIndexView, expose
from flask_admin import BaseView

from storage import (
    add_bad_word,
    delete_bad_word,
    get_required_channel,
    get_required_channel_message_limit,
    init_db,
    list_bad_words,
    set_setting,
)


ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")


BASE_CSS = """
<style>
  :root {
    --ink: #172026;
    --muted: #697580;
    --line: #dce3ea;
    --bg: #f6f8fb;
    --panel: #ffffff;
    --accent: #0f766e;
    --accent-dark: #115e59;
    --danger: #dc2626;
  }
  body {
    background:
      radial-gradient(circle at top left, rgba(15, 118, 110, .12), transparent 28rem),
      linear-gradient(180deg, #fbfcfe 0%, var(--bg) 100%);
    color: var(--ink);
    font-family: Vazirmatn, Tahoma, Arial, sans-serif;
  }
  .navbar, .navbar-default {
    background: rgba(255,255,255,.92) !important;
    border: 0;
    border-bottom: 1px solid var(--line);
    box-shadow: 0 14px 35px rgba(23, 32, 38, .06);
  }
  .navbar-brand, .nav-link, .navbar-nav > li > a {
    color: var(--ink) !important;
    font-weight: 700;
  }
  .container, .container-fluid { max-width: 1120px; }
  .admin-shell {
    direction: rtl;
    padding: 28px 4px 44px;
  }
  .hero {
    display: grid;
    gap: 10px;
    margin-bottom: 22px;
  }
  .hero h1 {
    margin: 0;
    font-size: clamp(28px, 4vw, 44px);
    font-weight: 900;
    letter-spacing: 0;
  }
  .hero p {
    margin: 0;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.9;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 14px;
  }
  .panel-card {
    background: rgba(255,255,255,.88);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 18px;
    box-shadow: 0 14px 36px rgba(23, 32, 38, .07);
  }
  .panel-card h2, .panel-card h3 {
    margin: 0 0 12px;
    font-size: 18px;
    font-weight: 900;
  }
  .metric {
    font-size: 34px;
    font-weight: 900;
    color: var(--accent-dark);
  }
  .muted {
    color: var(--muted);
    line-height: 1.8;
  }
  .admin-form {
    display: grid;
    gap: 12px;
  }
  .admin-form label {
    font-weight: 800;
    margin: 0;
  }
  .admin-form input {
    min-height: 44px;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 8px 12px;
    background: #fff;
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
    font-weight: 800;
    padding: 10px 16px;
  }
  .pretty-btn:hover {
    background: var(--accent-dark) !important;
    text-decoration: none;
  }
  .danger-btn {
    background: #fff;
    color: var(--danger);
    border: 1px solid rgba(220, 38, 38, .28);
    border-radius: 8px;
    padding: 7px 10px;
    font-weight: 800;
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
  }
  .word {
    font-weight: 900;
    overflow-wrap: anywhere;
  }
  .badge-soft {
    display: inline-flex;
    background: rgba(15, 118, 110, .10);
    color: var(--accent-dark);
    border: 1px solid rgba(15, 118, 110, .20);
    border-radius: 999px;
    padding: 5px 10px;
    font-weight: 800;
  }
  .alert {
    direction: rtl;
    border-radius: 8px;
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
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                session["admin_logged_in"] = True
                return redirect(url_for("admin.index"))
            flash("نام کاربری یا رمز عبور اشتباه است.", "danger")

        return render_template_string(
            BASE_CSS
            + """
            <main class="admin-shell" style="max-width: 460px; margin: 6vh auto;">
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
        if request.method == "POST":
            set_setting("required_channel", request.form.get("required_channel", ""))
            set_setting(
                "required_channel_message_limit",
                request.form.get("required_channel_message_limit", "5"),
            )
            flash("تنظیمات کانال ذخیره شد.", "success")
            return redirect(url_for(".index"))

        return self.render(
            "admin/settings.html",
            base_css=BASE_CSS,
            channel=get_required_channel(),
            limit=get_required_channel_message_limit(),
        )


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("ADMIN_PORT", "5000")))
