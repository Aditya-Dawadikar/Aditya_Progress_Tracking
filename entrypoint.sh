#!/bin/sh
set -e

python - <<'PY'
import os
from urllib.parse import urlsplit

source = "MONGO_PRIVATE_URL" if os.environ.get("MONGO_PRIVATE_URL") else "MONGO_URL"
uri = os.environ.get(source, "")
parts = urlsplit(uri)
try:
  port = parts.port or "<default>"
except ValueError:
  port = "<invalid>"


def display(value):
  return str(value)[:43]


print("+----------------------------------------------------------+")
print("|                 MONGODB STARTUP CONFIG                  |")
print("+----------------------------------------------------------+")
print(f"| Source:      {display(source):<43} |")
print(f"| Scheme:      {display(parts.scheme or '<missing>'):<43} |")
print(f"| Host:        {display(parts.hostname or '<missing>'):<43} |")
print(f"| Port:        {display(port):<43} |")
print(f"| Database:    {display(os.environ.get('MONGO_DB_NAME', 'goalpost')):<43} |")
print(f"| Credentials: {display(bool(parts.username or parts.password)):<43} |")
print("+----------------------------------------------------------+")
PY

python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}"