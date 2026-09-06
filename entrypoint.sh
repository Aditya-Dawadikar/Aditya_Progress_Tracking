#!/bin/sh
set -e

python - <<'PY'
import os
from urllib.parse import urlsplit

from pymongo import MongoClient

source = "MONGO_PRIVATE_URL" if os.environ.get("MONGO_PRIVATE_URL") else "MONGO_URL"
uri = os.environ.get(source, "")
database = os.environ.get("MONGO_DB_NAME", "goalpost")
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
print(f"| Database:    {display(database):<43} |")
print(f"| Credentials: {display(bool(parts.username or parts.password)):<43} |")
print("+----------------------------------------------------------+")

try:
  client = MongoClient(uri, serverSelectionTimeoutMS=5000)
  client.admin.command("ping")
except Exception as exc:
  print(f"MongoDB connection test: FAILED ({type(exc).__name__})", flush=True)
  raise
else:
  print("MongoDB connection test: SUCCESS", flush=True)
finally:
  if "client" in locals():
    client.close()
PY

python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}"