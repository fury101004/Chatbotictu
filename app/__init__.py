from __future__ import annotations

from typing import TYPE_CHECKING

from config import FLASK_DEBUG, FLASK_USE_RELOADER, ROOT_DIR, SECRET_KEY

if TYPE_CHECKING:
    from flask import Flask


def create_app() -> "Flask":
    from flask import Flask

    from app.models.history import init_db
    from app.routes.api import api_bp
    from app.routes.ui import ui_bp

    app = Flask(
        __name__,
        template_folder=str(ROOT_DIR / "templates"),
        static_folder=str(ROOT_DIR / "static"),
    )
    app.config["SECRET_KEY"] = SECRET_KEY

    init_db()

    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp)

    return app


def run() -> None:
    app = create_app()
    app.run(debug=FLASK_DEBUG, use_reloader=FLASK_USE_RELOADER)
