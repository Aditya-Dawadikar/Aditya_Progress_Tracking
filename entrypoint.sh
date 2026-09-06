#!/bin/sh
set -e

python - <<'PY'
import os
from urllib.parse import urlsplit

from pymongo import MongoClient

source = "MONGO_PRIVATE_URL" if os.environ.get("MONGO_PRIVATE_URL") else "MONGO_URL"
uri = os.environ.get(source, "")
parts = urlsplit(uri)
database = os.environ.get("MONGO_DB_NAME") or parts.path.lstrip("/") or "goalpost"
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
  client[database].list_collection_names()
except Exception as exc:
  print(f"MongoDB database authorization test: FAILED ({type(exc).__name__})", flush=True)
  raise
else:
  print("MongoDB database authorization test: SUCCESS", flush=True)
finally:
  if "client" in locals():
    client.close()
PY

python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}"