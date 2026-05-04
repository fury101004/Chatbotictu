# test.py — TOOL TEST CHAT SIÊU NHANH CMD (TU TIÊN 2025 – ĐÃ FIX SẠCH)
import os
import time

import requests

# ==================== CẤU HÌNH ====================
URL = "http://127.0.0.1:8000/chat"   # Cùng wifi thì đổi thành IP máy tính
TIMEOUT = 30

# Màu cho đẹp terminal (Windows 10+ & Linux/Mac đều chạy ngon)
Y = "\033[93m"   # Vàng
G = "\033[92m"   # Xanh lá
R = "\033[91m"   # Đỏ
B = "\033[96m"   # Cyan
W = "\033[0m"    # Reset

TEST_MESSAGES = [
    "Chào đạo hữu", "hello", "mày là ai", "giới thiệu đi", "cảm ơn", "bye",
    "đồ chó chết", "ngươi ngu lắm", "kể về linh đan", "làm sao phi thăng",
    "bí kíp luyện kiếm", "hahahaha", ":D", "ok đại ca",
]


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def send(msg: str):
    try:
        r = requests.post(URL, data={"message": msg}, timeout=TIMEOUT)
        if r.status_code == 200:
            reply = r.json().get("response", "...")
            print(f"{G}   Bot: {reply}{W}\n")
        else:
            print(f"{R}   Lỗi {r.status_code}: {r.text}{W}\n")
    except requests.exceptions.ConnectionError:
        print(f"{R}   Không kết nối được! Chạy uvicorn config.asgi:app --reload chưa đạo hữu?{W}\n")
    except requests.exceptions.Timeout:
        print(f"{Y}   Bot đang độ kiếp... nghĩ quá lâu rồi!{W}\n")
    except Exception as e:
        print(f"{R}   Lỗi: {e}{W}\n")


def interactive():
    print(f"{B}=== CHẾ ĐỘ CHAT TAY – gõ 'thoat' để thoát ==={W}\n")
    while True:
        try:
            msg = input(f"{Y}[Bạn]: {W}").strip()
            if msg.lower() in {"thoat", "exit", "quit", "bye"}:
                print(f"{G}\nPhi thăng thành công, hẹn gặp lại trên tiên giới!{W}\n")
                break
            if not msg:
                continue
            print()
            send(msg)
        except KeyboardInterrupt:
            print(f"\n\n{G}Thoát đột ngột, coi chừng tâm ma nhập!{W}\n")
            break


def auto():
    print(f"{B}=== AUTO TEST 14 CÂU TU TIÊN ==={W}\n")
    for i, msg in enumerate(TEST_MESSAGES, 1):
        print(f"{Y}{i:02d}. [Bạn]: {msg}{W}")
        send(msg)
        time.sleep(1.8)
    print(f"{G}=== TEST XONG – PHI THĂNG HOÀN TẤT! ==={W}\n")


# ==================== MAIN ====================
if __name__ == "__main__":
    clear()
    print(f"{B}{'=' * 56}")
    print("       TOOL TEST CHAT TU TIÊN 2025 – CMD EDITION")
    print("=" * 56 + f"{W}\n")

    choice = input(f"{B}Chọn: {W}1 (auto test) | {W}2 (chat tay){B} → ").strip() or "2"

    if choice == "1":
        auto()
    else:
        interactive()

    input(f"{Y}Nhấn Enter để thoát...{W}")


"""_Luồng xử lý câu hỏi của user

User gửi câu → chia nhỏ thành chunks → LLM lấy keyword → chuyển thành vector → đưa vào mô hình → xử lý → trả về vector → chuyển thành ngôn ngữ tự nhiên → trả user.

Ý 6 phần 2 – Ingest file

File.md được lưu vào botconfig.db.

LLM gom câu cùng 1 ý → chia thành chunks → lấy keyword → embed thành vector → lưu vectorstore/chroma.db.

Metadata (title, level, source, word_count)

title: tên heading chunk → hiển thị, phân loại.

level: cấp heading → sắp xếp, ưu tiên context quan trọng.

source: file gốc → filter khi nhắc file cụ thể.

word_count: số từ → preview, thống kê, cân nhắc quan trọng.

Luồng dùng metadata

Upload → chunk + metadata.

Query → filter/ưu tiên chunk dựa trên source, title, level; dùng word_count để preview.

Quản lý vector → nhóm theo file (source), sắp xếp theo level, hiển thị preview (word_count).
"""
