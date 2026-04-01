from flask import Blueprint, render_template


ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/")
def home():
    return render_template("home.html", active="home", title="Home")


@ui_bp.route("/chat-ui")
def chat_ui():
    return render_template("chat.html", active="chat", title="Chat")


@ui_bp.route("/upload")
def upload():
    return render_template("upload.html", active="upload", title="Upload")


@ui_bp.route("/vector")
def vector():
    return render_template("vector.html", active="vector", title="Vector")


@ui_bp.route("/config")
def config_view():
    return render_template("config.html", active="config", title="Config")


@ui_bp.route("/history")
def history_view():
    return render_template("history.html", active="history", title="History")

