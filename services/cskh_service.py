# cskh_system.py – HỆ THỐNG CHUYỂN CSKH TỰ ĐỘNG CHO CHATBOT
from typing import Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
import uuid
import json
from markupsafe import Markup

active_customers: Dict[str, dict] = {}
cskh_websocket: Optional[WebSocket] = None

def is_customer_support_intent(message: str) -> bool:
    msg = message.lower().strip()
    
    trigger_words = [
        # Từ tắt – khách hay gõ nhất
        "cskh", "nhân viên", "người thật", "gặp người", "zalo", "facebook",
        "hotline", "gọi", "liên hệ", "ship", "giao", "mua", "đặt",
        "đặt hàng", "giao hàng", "vận chuyển", "đổi trả", "bảo hành",
        "giá", "bao nhiêu", "tiền", "khuyến mãi", "thanh toán", "hóa đơn",
        "lỗi", "hỏng", "khiếu nại", "đơn hàng", "chuyển khoản", "cod", "size", "còn hàng"
    ]
    
    return any(word in msg for word in trigger_words)

async def register_cskh_routes(app, templates):
    @app.get("/cskh-panel", response_class=HTMLResponse)
    async def cskh_panel_page(request: Request):
        return templates.TemplateResponse("pages/cskh_panel.html", {"request": request})

    # ==================== PANEL CSKH ====================
    @app.websocket("/ws-cskh")
    async def ws_cskh(websocket: WebSocket):
        global cskh_websocket
        await websocket.accept()                    # ← BẮT BUỘC
        cskh_websocket = websocket
        await websocket.send_text(json.dumps({"type": "count", "count": len(active_customers)}))

        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "reply":
                    session_id = msg["session_id"]
                    customer = active_customers.get(session_id)
                    if not customer: 
                        continue

                    payload = json.dumps({
                        "from": "cskh",
                        "message": msg["message"],
                        "trigger_floating": True
                    })

                    if customer.get("ws") and customer.get("confirmed"):
                        await customer["ws"].send_text(payload)
                    else:
                        customer.setdefault("message_queue", []).append(msg["message"])
        except WebSocketDisconnect:
            cskh_websocket = None

    # ==================== KHÁCH HÀNG KẾT NỐI ====================
    @app.websocket("/ws-customer/{session_id}")
    async def ws_customer(websocket: WebSocket, session_id: str):
        # ← DÒNG QUAN TRỌNG NHẤT – PHẢI ACCEPT TRƯỚC KHI SEND GÌ CẢ
        await websocket.accept()                    # ← ĐÂY LÀ DÒNG BỊ THIẾU!!!

        if session_id not in active_customers:
            await websocket.close(code=1008)
            return

        customer = active_customers[session_id]
        customer["ws"] = websocket
        customer["confirmed"] = True

        # Gửi lại các tin nhắn bị lỡ (nếu có)
        if customer.get("message_queue"):
            for queued_msg in customer["message_queue"]:
                await websocket.send_text(json.dumps({
                    "from": "cskh",
                    "message": queued_msg,
                    "trigger_floating": True
                }))
            customer.pop("message_queue", None)

        # Thông báo cho panel CSKH biết khách đã kết nối
        if cskh_websocket:
            await cskh_websocket.send_text(json.dumps({
                "type": "customer_connected",
                "session_id": session_id,
                "name": customer.get("name", "Khách")
            }))

        try:
            while True:
                data = await websocket.receive_text()
                if cskh_websocket:
                    await cskh_websocket.send_text(json.dumps({
                        "type": "message",
                        "session_id": session_id,
                        "message": data
                    }))
        except WebSocketDisconnect:
            customer["ws"] = None
            customer["confirmed"] = False
            if cskh_websocket:
                await cskh_websocket.send_text(json.dumps({
                    "type": "customer_disconnected",
                    "session_id": session_id
                }))

# ==================== CHUYỂN CSKH ====================
async def handle_cskh_transfer(message: str, customer_name: str = "Khách hàng", force: bool = True):
    session_id = str(uuid.uuid4())[-8:]

    active_customers[session_id] = {
        "ws": None,
        "first_msg": message,
        "name": customer_name,
        "confirmed": False,
        "message_queue": []
    }

    # Thông báo có khách mới cho panel
    if cskh_websocket:
        await cskh_websocket.send_text(json.dumps({
            "type": "new_customer",
            "session_id": session_id,
            "message": message,
            "name": customer_name
        }))

    if force:
        html = f"""
        <div style="text-align:center;padding:15px;background:#00ff8833;border-radius:12px;margin:15px 0;">
            <h3 style="color:#00ff88;margin:0;">Đã kết nối với nhân viên hỗ trợ thật 100%!</h3>
            <p style="color:#ccc;margin:5px 0 0;">Nhân viên sẽ trả lời ngay trong khung chat này</p>
        </div>
        <script>
            if (typeof window.connectToCSKH === "function") {{
                window.connectToCSKH("{session_id}", {json.dumps(message)});
            }}
        </script>
        """
        return {
            "response": Markup(html),
            "is_cskh": True,
            "session_id": session_id
        }
    return None



