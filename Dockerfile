FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BOT_DB_PATH=/data/bot_settings.sqlite3

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data && chown -R app:app /app /data

USER app

EXPOSE 5000

CMD ["python", "bot.py"]
