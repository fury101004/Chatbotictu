from __future__ import annotations

from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if payload.get("sub") != "partner":
        raise HTTPException(status_code=401, detail="Invalid token subject")

    return credentials


def create_partner_token() -> str:
    return jwt.encode(
        {"exp": datetime.utcnow() + timedelta(hours=24), "sub": "partner"},
        settings.JWT_SECRET,
        algorithm="HS256",
    )

