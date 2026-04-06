from config.app_factory import create_app

app = create_app()

templates = app.state.templates

__all__ = ["app", "templates"]
