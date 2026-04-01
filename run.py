from app import create_app
from config import FLASK_DEBUG, FLASK_USE_RELOADER


app = create_app()


if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG, use_reloader=FLASK_USE_RELOADER)

