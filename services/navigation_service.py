from __future__ import annotations

from typing import TypedDict


class MenuItem(TypedDict):
    label: str
    path: str
    icon: str
    icon_svg: str
    active_paths: tuple[str, ...]


def _icon_svg(body: str) -> str:
    return (
        '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true" '
        'focusable="false">'
        f"{body}</svg>"
    )


NAV_ICONS: dict[str, str] = {
    "home": _icon_svg(
        '<path d="m3 10.5 9-7 9 7"></path>'
        '<path d="M5 10v10h5v-6h4v6h5V10"></path>'
    ),
    "message-circle": _icon_svg(
        '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 17 0Z"></path>'
    ),
    "upload": _icon_svg(
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<path d="M17 8 12 3 7 8"></path>'
        '<path d="M12 3v12"></path>'
    ),
    "database": _icon_svg(
        '<ellipse cx="12" cy="5" rx="8" ry="3"></ellipse>'
        '<path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"></path>'
        '<path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"></path>'
    ),
    "book-open": _icon_svg(
        '<path d="M2 5.5A2.5 2.5 0 0 1 4.5 3H10a2 2 0 0 1 2 2v16a2 2 0 0 0-2-2H4.5A2.5 2.5 0 0 1 2 16.5z"></path>'
        '<path d="M22 5.5A2.5 2.5 0 0 0 19.5 3H14a2 2 0 0 0-2 2v16a2 2 0 0 1 2-2h5.5a2.5 2.5 0 0 0 2.5-2.5z"></path>'
    ),
    "settings": _icon_svg(
        '<path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"></path>'
        '<path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1A2 2 0 1 1 4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.3 7A2 2 0 1 1 7.1 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1A2 2 0 1 1 19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1a2 2 0 1 1 0 4H21a1.7 1.7 0 0 0-1.6 1Z"></path>'
    ),
    "history": _icon_svg(
        '<path d="M3 12a9 9 0 1 0 3-6.7"></path>'
        '<path d="M3 3v6h6"></path>'
        '<path d="M12 7v5l3 2"></path>'
    ),
    "activity": _icon_svg(
        '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>'
    ),
    "log-out": _icon_svg(
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>'
        '<path d="M16 17l5-5-5-5"></path>'
        '<path d="M21 12H9"></path>'
    ),
    "sun": _icon_svg(
        '<circle cx="12" cy="12" r="4"></circle>'
        '<path d="M12 2v2"></path>'
        '<path d="M12 20v2"></path>'
        '<path d="m4.93 4.93 1.41 1.41"></path>'
        '<path d="m17.66 17.66 1.41 1.41"></path>'
        '<path d="M2 12h2"></path>'
        '<path d="M20 12h2"></path>'
        '<path d="m6.34 17.66-1.41 1.41"></path>'
        '<path d="m19.07 4.93-1.41 1.41"></path>'
    ),
    "moon": _icon_svg('<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"></path>'),
}


ADMIN_MENU_CONFIG = (
    {"label": "Trang chủ", "path": "/", "icon": "home", "active_paths": ("/",)},
    {"label": "Trò chuyện", "path": "/chat", "icon": "message-circle", "active_paths": ("/chat",)},
    {"label": "Upload kiến thức", "path": "/data-loader", "icon": "upload", "active_paths": ("/data-loader", "/upload")},
    {
        "label": "Kho vector",
        "path": "/vector-manager",
        "icon": "database",
        "active_paths": ("/vector-manager", "/vector-store"),
    },
    {
        "label": "Kho tri thức",
        "path": "/knowledge-base",
        "icon": "book-open",
        "active_paths": ("/knowledge-base", "/knowledge"),
    },
    {"label": "Cấu hình", "path": "/config", "icon": "settings", "active_paths": ("/config", "/settings")},
    {"label": "Đánh giá", "path": "/evaluation-dashboard", "icon": "activity", "active_paths": ("/evaluation-dashboard",)},
    {"label": "Lịch sử chat", "path": "/history", "icon": "history", "active_paths": ("/history",)},
)

USER_MENU_CONFIG = (
    {"label": "Trò chuyện", "path": "/chat", "icon": "message-circle", "active_paths": ("/chat",)},
    {"label": "Lịch sử chat", "path": "/history", "icon": "history", "active_paths": ("/history",)},
)


def _with_icon(item: dict[str, object]) -> MenuItem:
    icon_name = str(item["icon"])
    return {
        "label": str(item["label"]),
        "path": str(item["path"]),
        "icon": icon_name,
        "icon_svg": NAV_ICONS[icon_name],
        "active_paths": tuple(str(path) for path in item["active_paths"]),
    }


def get_menu_items(role: str) -> list[MenuItem]:
    config = ADMIN_MENU_CONFIG if role == "admin" else USER_MENU_CONFIG if role in {"user", "student"} else ()
    return [_with_icon(item) for item in config]


def get_logout_label(role: str) -> str:
    return "Đăng xuất admin" if role == "admin" else "Đăng xuất"
