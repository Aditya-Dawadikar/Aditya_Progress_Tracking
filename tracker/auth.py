"""Issues and verifies the JWT that gates the whole app behind one shared
password. See AppPasswordMiddleware (tracker/middleware.py) for enforcement
and views.app_login/app_logout for the login flow itself.
"""

import time

import jwt
from django.conf import settings

ALGORITHM = "HS256"


def issue_token():
    now = int(time.time())
    payload = {"app_auth": True, "iat": now, "exp": now + settings.JWT_MAX_AGE_SECONDS}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token):
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return False
    return bool(payload.get("app_auth"))
