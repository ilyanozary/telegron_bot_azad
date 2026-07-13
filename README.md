# Telegram Group Manager Bot

این ربات برای مدیریت گروه ساخته شده و دو قابلیت اصلی دارد:

- خوش‌آمدگویی به اعضای جدید
- تشخیص فحاشی و حذف پیام
- آنتی‌اسپم (حذف پیام اسپم + میوت موقت)
- استثنا برای ادمین‌ها (هیچ محدودیتی روی ادمین/سازنده اعمال نمی‌شود)
- پنل ادمین تحت وب برای مدیریت کلمات ممنوعه و کانال اجباری
- ویرایش متن پیام‌های ربات از داخل پنل ادمین
- الزام عضویت در کانال: اگر کاربر عضو کانال تعریف‌شده نباشد، بعد از ۵ پیام، پیام آخرش حذف می‌شود و لینک عضویت می‌گیرد.

## راه‌اندازی

### اجرا با Docker

1. فایل تنظیمات را بسازید:

   ```bash
   cp .env.example .env
   ```

2. مقدارهای داخل `.env` را کامل کنید:

   ```env
   BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=CHANGE_ME
   ADMIN_SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_SECRET
   ```

3. سرویس‌ها را بالا بیاورید:

   ```bash
   docker compose up -d --build
   ```

4. پنل ادمین:

   ```text
   http://localhost:5000/admin
   ```

5. دیدن لاگ‌ها:

   ```bash
   docker compose logs -f
   ```

6. خاموش کردن سرویس‌ها:

   ```bash
   docker compose down
   ```

داده‌های پنل و کلمات ممنوعه داخل volume به نام `bot_data` ذخیره می‌شود و با ری‌استارت کانتینرها باقی می‌ماند.

### اجرای مستقیم با Python

1. ساخت محیط مجازی:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. نصب وابستگی‌ها:

   ```bash
   pip install -r requirements.txt
   ```

3. تنظیم توکن:

   ```bash
   export BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
   ```

4. اجرای ربات:

   ```bash
   python bot.py
   ```

5. اجرای پنل ادمین:

   ```bash
   export ADMIN_USERNAME="admin"
   export ADMIN_PASSWORD="CHANGE_ME"
   export ADMIN_SECRET_KEY="CHANGE_ME_SECRET"
   flask --app admin_panel run --host 0.0.0.0 --port 5000
   ```

   سپس وارد آدرس زیر شوید:

   ```text
   http://localhost:5000/admin
   ```

## نکات مهم

- ربات را در گروه **ادمین** کنید.
- دسترسی‌های زیر را به ربات بدهید:
  - Delete Messages
  - Restrict Members
- لیست فحش‌ها داخل فایل `bad_words.txt` است. هر خط یک کلمه یا عبارت.
  - در اجرای جدید، این فایل فقط بار اول وارد دیتابیس SQLite می‌شود.
  - بعد از آن، مدیریت کلمات از پنل انجام می‌شود.
- تنظیم کانال اجباری از پنل ادمین انجام می‌شود.
  - می‌توانید چند کانال وارد کنید؛ هر خط یک کانال.
  - برای کانال عمومی، مقدار را مثل `@your_channel` یا `https://t.me/your_channel` وارد کنید.
  - بعد از ذخیره، پنل تک‌تک کانال‌ها را بررسی می‌کند که ربات داخلشان ادمین هست یا نه.
  - اگر ربات در کانالی ادمین نباشد، پنل پیام هشدار همان کانال را نشان می‌دهد؛ وقتی ادمین شد و دوباره ذخیره/بررسی کنید، پیام موفقیت نمایش داده می‌شود.
  - برای اینکه ربات بتواند عضویت کاربران را چک کند، ربات باید داخل همه کانال‌های اجباری ادمین باشد.
- متن پیام‌های گروه از صفحه «پیام‌های ربات» در پنل قابل تغییر است.
  - `{user}` نام کاربر را وارد می‌کند.
  - `{channel}` لینک یا عنوان کانال را وارد می‌کند.
  - `{minutes}` مدت میوت اسپم را وارد می‌کند.
- تنظیمات آنتی‌اسپم داخل `bot.py` قابل تغییر است:
  - `SPAM_WINDOW_SECONDS` و `SPAM_MAX_MESSAGES` برای فلود
  - `SPAM_REPEAT_WINDOW_SECONDS` و `SPAM_REPEAT_MAX` برای تکرار پیام
  - `SPAM_MUTE_SECONDS` مدت میوت

## دیتابیس

تنظیمات پنل و کلمات ممنوعه در فایل `bot_settings.sqlite3` ذخیره می‌شود.
اگر خواستید مسیر دیتابیس را عوض کنید:

```bash
export BOT_DB_PATH="/path/to/bot_settings.sqlite3"
```
