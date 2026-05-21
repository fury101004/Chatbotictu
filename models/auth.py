from __future__ import annotations

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    full_name: str
    username: str
    password: str
    confirm_password: str


class RegisterResponse(BaseModel):
    status: str
    message: str
