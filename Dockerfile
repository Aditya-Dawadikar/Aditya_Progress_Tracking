FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

# DEBUG=False so this picks whitenoise's hashed/compressed manifest storage
# (the one actually used in production). Real SECRET_KEY comes from Railway
# at runtime — this placeholder only needs to satisfy Django at build time.
RUN DEBUG=False SECRET_KEY=build-time-only python manage.py collectstatic --noinput

# Runs as root deliberately: Railway volumes mount root-owned, and a non-root
# user here can't write to a mounted SQLITE_PATH. Not a multi-tenant service,
# so the usual "drop root" advice costs more (silent write failures) than it buys.
EXPOSE 8000

CMD ["./entrypoint.sh"]
