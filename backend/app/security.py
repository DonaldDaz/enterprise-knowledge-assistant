import os
from datetime import datetime, timedelta, timezone
from hmac import compare_digest

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from .config import ROLES, settings

bearer = OAuth2PasswordBearer(tokenUrl="/api/login")


def authenticate(username: str, password: str):
    if username not in ROLES:
        return None
    expected = os.environ[f"{username.upper()}_PASSWORD"]
    if not compare_digest(password, expected):
        return None
    token = jwt.encode({"sub": username, "role": username, "exp": datetime.now(timezone.utc) + timedelta(hours=8)}, settings.jwt_secret, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer", "username": username, "role": username}


def current_user(token: str = Depends(bearer)) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("sub") not in ROLES or payload.get("role") != payload.get("sub"):
            raise ValueError("invalid role")
        return {"username": payload["sub"], "role": payload["role"]}
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(401, "Sessione non valida", headers={"WWW-Authenticate": "Bearer"}) from exc


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Accesso riservato agli amministratori")
    return user
