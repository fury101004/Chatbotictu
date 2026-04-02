from __future__ import annotations

from pathlib import Path
from typing import Union


RouteValue = str
PathLike = Union[str, Path]

SOURCE_ROUTES = ("all", "policy", "handbook")
HANDBOOK_SOURCE_ROOTS = {"S\u1ed5 tay sinh vi\u00ean c\u00e1c n\u0103m"}
UPLOAD_SOURCE_ROOTS = {"_uploads", "uploads", "user_uploads"}


def normalize_source_route(route: str | None) -> RouteValue:
    value = (route or "all").strip().lower()
    if value not in SOURCE_ROUTES:
        raise ValueError(f"Unsupported source route: {route}")
    return value


def source_route_from_relative_path(relative_path: PathLike) -> RouteValue:
    path = Path(relative_path)
    if path.parts and path.parts[0] in HANDBOOK_SOURCE_ROOTS:
        return "handbook"
    if path.parts and path.parts[0].lower() in UPLOAD_SOURCE_ROOTS and len(path.parts) >= 2:
        uploaded_route = path.parts[1].strip().lower()
        if uploaded_route in {"policy", "handbook"}:
            return uploaded_route
    return "policy"


def route_matches_relative_path(relative_path: PathLike, route: str | None) -> bool:
    normalized_route = normalize_source_route(route)
    if normalized_route == "all":
        return True
    return source_route_from_relative_path(relative_path) == normalized_route
