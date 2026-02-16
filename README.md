# Telegram Group Manager Bot

این ربات برای مدیریت گروه ساخته شده و دو قابلیت اصلی دارد:

- خوش‌آمدگویی به اعضای جدید
- تشخیص فحاشی و بن کردن کاربر
- آنتی‌اسپم (حذف پیام اسپم + میوت موقت)
- استثنا برای ادمین‌ها (هیچ محدودیتی روی ادمین/سازنده اعمال نمی‌شود)

## راه‌اندازی

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

## نکات مهم

- ربات را در گروه **ادمین** کنید.
- دسترسی‌های زیر را به ربات بدهید:
  - Delete Messages
  - Ban Users
- لیست فحش‌ها داخل فایل `bad_words.txt` است. هر خط یک کلمه یا عبارت.
- تنظیمات آنتی‌اسپم داخل `bot.py` قابل تغییر است:
  - `SPAM_WINDOW_SECONDS` و `SPAM_MAX_MESSAGES` برای فلود
  - `SPAM_REPEAT_WINDOW_SECONDS` و `SPAM_REPEAT_MAX` برای تکرار پیام
  - `SPAM_MUTE_SECONDS` مدت میوت
