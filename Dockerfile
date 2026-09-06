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
# at runtime. MONGO_URL is only needed so settings can load during collection;
# collectstatic does not open a database connection.
RUN DEBUG=False SECRET_KEY=build-time-only MONGO_URL=mongodb://localhost:27017 \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["./entrypoint.sh"]
