from __future__ import annotations

from fastapi import FastAPI

from services.cskh_service import register_cskh_routes as _register_cskh_routes


async def register_cskh_routes(app: FastAPI, templates) -> None:
    await _register_cskh_routes(app, templates)

