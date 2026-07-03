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
  .admin-form input {
    width: 100%;
    min-height: 46px;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 9px 12px;
    background: #fff;
    color: var(--ink);
    box-shadow: inset 0 1px 2px rgba(15, 23, 42, .03);
  }
  .admin-form input:focus {
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
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
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
