from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, request, send_file, session

from app.services.chat_service import process_chat_message
from app.services.history_service import (
    clear_user_history,
    export_history_as_pdf,
    export_history_as_txt,
    list_history_for_api,
)


api_bp = Blueprint("api", __name__)


def _get_user_id() -> str:
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
    return session["user_id"]


@api_bp.route("/api/history")
def api_history():
    user_id = _get_user_id()
    return jsonify(list_history_for_api(user_id))


@api_bp.route("/api/history/clear", methods=["POST"])
def api_clear_history():
    user_id = _get_user_id()
    clear_user_history(user_id)
    return jsonify({"status": "ok"})


@api_bp.route("/api/history/export/txt")
def export_txt():
    user_id = _get_user_id()
    buffer = export_history_as_txt(user_id)
    return send_file(buffer, as_attachment=True, download_name="chat_history.txt")


@api_bp.route("/api/history/export/pdf")
def export_pdf():
    user_id = _get_user_id()
    buffer = export_history_as_pdf(user_id)
    return send_file(buffer, as_attachment=True, download_name="chat_history.pdf")


@api_bp.route("/chat", methods=["POST"])
def chat_api():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()

    if not message:
        return jsonify({"error": "Tin nhan khong duoc de trong."}), 400

    user_id = _get_user_id()

    try:
        result = process_chat_message(user_id, message)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Khong the xu ly yeu cau luc nay."}), 500

    return jsonify(
        {
            "reply": result["answer"],
            "route": result["route"],
            "agent": result.get("agent", result["route"]),
            "agent_label": result.get("agent_label", result["route"]),
            "sources": result.get("sources", []),
        }
    )
