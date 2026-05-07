"""Controller package."""

from controllers.api_controller import register_api_routes
from controllers.web_controller import register_web_routes

__all__ = ["register_api_routes", "register_web_routes"]
