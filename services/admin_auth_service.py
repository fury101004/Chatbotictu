from __future__ import annotations

from dataclasses import dataclass
import hmac
import sqlite3
from urllib.parse import quote_plus

import bcrypt
from fastapi import Request
from fastapi.responses import RedirectResponse

from config.db import (
    add_web_user,
    delete_web_user,
    get_web_user_by_id,
    get_web_user_by_username,
    list_web_users,
    update_web_user,
)
from config.settings import settings


ADMIN_SESSION_KEY = "admin_authenticated"
ADMIN_USER_KEY = "admin_username"
ADMIN_ROLE_KEY = "admin_role"
AUTH_SESSION_KEY = "web_authenticated"
AUTH_USER_KEY = "web_username"
AUTH_ROLE_KEY = "web_role"

ADMIN_ROLE = "admin"
USER_ROLES = {"user", "student"}
DEFAULT_REGISTERED_ROLE = "user"
MIN_REGISTER_PASSWORD_LENGTH = 6


@dataclass(frozen=True)
class RegistrationResult:
    ok: bool
    message: str
    code: str = "ok"


@dataclass(frozen=True)
class UserManagementResult:
    ok: bool
    message: str
    code: str = "ok"


def normalize_role(role: str | None) -> str:
    normalized = str(role or "").strip().lower()
    if normalized == settings.ADMIN_ROLE.strip().lower() or normalized == ADMIN_ROLE:
        return ADMIN_ROLE
    if normalized in USER_ROLES:
        return normalized
    return "guest"


def get_current_role(request: Request) -> str:
    authenticated = bool(request.session.get(AUTH_SESSION_KEY) or request.session.get(ADMIN_SESSION_KEY))
    if not authenticated:
        return "guest"
    if request.session.get(ADMIN_SESSION_KEY) and not request.session.get(AUTH_ROLE_KEY):
        return ADMIN_ROLE
    return normalize_role(request.session.get(AUTH_ROLE_KEY) or request.session.get(ADMIN_ROLE_KEY))


def get_current_username(request: Request) -> str:
    if request.session.get(AUTH_SESSION_KEY):
        return str(request.session.get(AUTH_USER_KEY) or "").strip()
    if request.session.get(ADMIN_SESSION_KEY):
        return str(request.session.get(ADMIN_USER_KEY) or "").strip()
    return ""


def is_web_authenticated(request: Request) -> bool:
    return get_current_role(request) in {ADMIN_ROLE, *USER_ROLES}


def is_admin_authenticated(request: Request) -> bool:
    return get_current_role(request) == ADMIN_ROLE


def authenticate_admin(username: str, password: str) -> bool:
    return hmac.compare_digest(username.strip(), settings.ADMIN_USERNAME) and hmac.compare_digest(
        password,
        settings.ADMIN_PASSWORD,
    )


def authenticate_user(username: str, password: str) -> bool:
    return hmac.compare_digest(username.strip(), settings.USER_USERNAME) and hmac.compare_digest(
        password,
        settings.USER_PASSWORD,
    )


def _normalize_username(username: str | None) -> str:
    return str(username or "").strip()


def _configured_account_exists(username: str) -> bool:
    normalized = _normalize_username(username).lower()
    return normalized in {
        settings.ADMIN_USERNAME.strip().lower(),
        settings.USER_USERNAME.strip().lower(),
    }


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def authenticate_web_user(username: str, password: str) -> str | None:
    if authenticate_admin(username, password):
        return ADMIN_ROLE
    if authenticate_user(username, password):
        return normalize_role(settings.USER_ROLE)
    stored_user = get_web_user_by_username(username)
    if stored_user and _verify_password(password, stored_user["password_hash"]):
        role = normalize_role(stored_user.get("role"))
        return role if role in USER_ROLES else DEFAULT_REGISTERED_ROLE
    return None


def register_web_user(full_name: str, username: str, password: str, confirm_password: str) -> RegistrationResult:
    cleaned_full_name = str(full_name or "").strip()
    cleaned_username = _normalize_username(username)
    raw_password = str(password or "")
    raw_confirm = str(confirm_password or "")

    if not cleaned_full_name or not cleaned_username or not raw_password or not raw_confirm:
        return RegistrationResult(False, "Vui lòng nhập đầy đủ thông tin bắt buộc.", "missing_fields")
    if raw_password != raw_confirm:
        return RegistrationResult(False, "Mật khẩu không khớp.", "password_mismatch")
    if len(raw_password) < MIN_REGISTER_PASSWORD_LENGTH:
        return RegistrationResult(
            False,
            f"Mật khẩu phải có ít nhất {MIN_REGISTER_PASSWORD_LENGTH} ký tự.",
            "weak_password",
        )
    if _configured_account_exists(cleaned_username) or get_web_user_by_username(cleaned_username):
        return RegistrationResult(False, "Tài khoản đã tồn tại.", "duplicate")

    try:
        add_web_user(
            full_name=cleaned_full_name,
            username=cleaned_username,
            password_hash=_hash_password(raw_password),
            role=DEFAULT_REGISTERED_ROLE,
        )
    except sqlite3.IntegrityError:
        return RegistrationResult(False, "Tài khoản đã tồn tại.", "duplicate")
    except ValueError:
        return RegistrationResult(False, "Mật khẩu không hợp lệ.", "invalid_password")

    return RegistrationResult(True, "Đăng ký thành công. Vui lòng đăng nhập.")


def _validate_managed_user_fields(
    *,
    full_name: str,
    username: str,
    role: str,
    password: str | None = None,
    password_required: bool = False,
) -> tuple[UserManagementResult | None, dict[str, str]]:
    cleaned_full_name = str(full_name or "").strip()
    cleaned_username = _normalize_username(username)
    normalized_role = normalize_role(role)
    raw_password = "" if password is None else str(password or "")

    if not cleaned_full_name or not cleaned_username:
        return UserManagementResult(False, "Vui lòng nhập đầy đủ họ tên và tài khoản.", "missing_fields"), {}
    if normalized_role not in USER_ROLES:
        return UserManagementResult(False, "Quyền user không hợp lệ.", "invalid_role"), {}
    if password_required and not raw_password:
        return UserManagementResult(False, "Vui lòng nhập mật khẩu.", "missing_password"), {}
    if raw_password and len(raw_password) < MIN_REGISTER_PASSWORD_LENGTH:
        return UserManagementResult(
            False,
            f"Mật khẩu phải có ít nhất {MIN_REGISTER_PASSWORD_LENGTH} ký tự.",
            "weak_password",
        ), {}
    return None, {
        "full_name": cleaned_full_name,
        "username": cleaned_username,
        "role": normalized_role,
        "password": raw_password,
    }


def get_user_management_payload() -> dict[str, list[dict[str, str | bool]]]:
    configured_accounts: list[dict[str, str | bool]] = [
        {
            "id": "configured-admin",
            "full_name": "Administrator",
            "username": settings.ADMIN_USERNAME,
            "role": ADMIN_ROLE,
            "created_at": "",
            "source": "config",
            "source_label": "Hệ thống",
            "can_edit": False,
            "can_delete": False,
        },
        {
            "id": "configured-user",
            "full_name": "Default user",
            "username": settings.USER_USERNAME,
            "role": normalize_role(settings.USER_ROLE),
            "created_at": "",
            "source": "config",
            "source_label": "Hệ thống",
            "can_edit": False,
            "can_delete": False,
        },
    ]
    stored_accounts: list[dict[str, str | bool]] = [
        {
            **user,
            "source": "database",
            "source_label": "Đăng ký",
            "can_edit": True,
            "can_delete": True,
        }
        for user in list_web_users()
    ]
    return {"users": [*configured_accounts, *stored_accounts]}


def create_managed_user(
    full_name: str,
    username: str,
    password: str,
    role: str = DEFAULT_REGISTERED_ROLE,
) -> UserManagementResult:
    error, fields = _validate_managed_user_fields(
        full_name=full_name,
        username=username,
        role=role,
        password=password,
        password_required=True,
    )
    if error:
        return error
    if _configured_account_exists(fields["username"]) or get_web_user_by_username(fields["username"]):
        return UserManagementResult(False, "Tài khoản đã tồn tại.", "duplicate")
    try:
        add_web_user(
            full_name=fields["full_name"],
            username=fields["username"],
            password_hash=_hash_password(fields["password"]),
            role=fields["role"],
        )
    except sqlite3.IntegrityError:
        return UserManagementResult(False, "Tài khoản đã tồn tại.", "duplicate")
    except ValueError:
        return UserManagementResult(False, "Dữ liệu user không hợp lệ.", "invalid")
    return UserManagementResult(True, "Đã tạo user mới.")


def update_managed_user(
    user_id: int,
    *,
    full_name: str,
    username: str,
    role: str,
    password: str = "",
) -> UserManagementResult:
    existing = get_web_user_by_id(user_id)
    if not existing:
        return UserManagementResult(False, "Không tìm thấy user.", "not_found")
    error, fields = _validate_managed_user_fields(
        full_name=full_name,
        username=username,
        role=role,
        password=password,
        password_required=False,
    )
    if error:
        return error

    if _configured_account_exists(fields["username"]):
        return UserManagementResult(False, "Tài khoản này trùng với tài khoản hệ thống.", "duplicate")
    duplicate = get_web_user_by_username(fields["username"])
    if duplicate and str(duplicate.get("id")) != str(existing["id"]):
        return UserManagementResult(False, "Tài khoản đã tồn tại.", "duplicate")

    try:
        changed = update_web_user(
            user_id,
            full_name=fields["full_name"],
            username=fields["username"],
            role=fields["role"],
            password_hash=_hash_password(fields["password"]) if fields["password"] else None,
        )
    except sqlite3.IntegrityError:
        return UserManagementResult(False, "Tài khoản đã tồn tại.", "duplicate")
    if not changed:
        return UserManagementResult(False, "Không tìm thấy user.", "not_found")
    return UserManagementResult(True, "Đã cập nhật user.")


def delete_managed_user(user_id: int) -> UserManagementResult:
    if not get_web_user_by_id(user_id):
        return UserManagementResult(False, "Không tìm thấy user.", "not_found")
    if not delete_web_user(user_id):
        return UserManagementResult(False, "Không tìm thấy user.", "not_found")
    return UserManagementResult(True, "Đã xóa user.")


def login_with_role(request: Request, username: str, role: str) -> None:
    normalized_role = normalize_role(role)
    request.session[AUTH_SESSION_KEY] = True
    request.session[AUTH_USER_KEY] = username.strip()
    request.session[AUTH_ROLE_KEY] = normalized_role

    if normalized_role == ADMIN_ROLE:
        request.session[ADMIN_SESSION_KEY] = True
        request.session[ADMIN_USER_KEY] = username.strip()
        request.session[ADMIN_ROLE_KEY] = settings.ADMIN_ROLE
    else:
        request.session.pop(ADMIN_SESSION_KEY, None)
        request.session.pop(ADMIN_USER_KEY, None)
        request.session.pop(ADMIN_ROLE_KEY, None)


def login_admin(request: Request, username: str) -> None:
    login_with_role(request, username, ADMIN_ROLE)


def logout_admin(request: Request) -> None:
    logout_web_user(request)


def logout_web_user(request: Request) -> None:
    request.session.pop(AUTH_SESSION_KEY, None)
    request.session.pop(AUTH_USER_KEY, None)
    request.session.pop(AUTH_ROLE_KEY, None)
    request.session.pop(ADMIN_SESSION_KEY, None)
    request.session.pop(ADMIN_USER_KEY, None)
    request.session.pop(ADMIN_ROLE_KEY, None)


def default_route_for_role(role: str) -> str:
    normalized_role = normalize_role(role)
    if normalized_role == ADMIN_ROLE or normalized_role in USER_ROLES:
        return "/"
    return "/login"


def admin_login_redirect(request: Request) -> RedirectResponse:
    next_path = str(request.url.path or "/")
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(f"/login?next={quote_plus(next_path)}", status_code=303)


def login_redirect(request: Request) -> RedirectResponse:
    return admin_login_redirect(request)
