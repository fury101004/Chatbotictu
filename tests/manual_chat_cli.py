# test.py â€” TOOL TEST CHAT SIĂU NHANH CMD (TU TIĂN 2025 â€“ ÄĂƒ FIX Sáº CH)
import requests
import os
import time

# ==================== Cáº¤U HĂŒNH ====================
URL = "http://127.0.0.1:8000/chat"   # CĂ¹ng wifi thĂ¬ Ä‘á»•i thĂ nh IP mĂ¡y tĂ­nh
TIMEOUT = 30

# MĂ u cho Ä‘áº¹p terminal (Windows 10+ & Linux/Mac Ä‘á»u cháº¡y ngon)
Y = "\033[93m"   # VĂ ng
G = "\033[92m"   # Xanh lĂ¡
R = "\033[91m"   # Äá»
B = "\033[96m"   # Cyan
W = "\033[0m"    # Reset

TEST_MESSAGES = [
    "ChĂ o Ä‘áº¡o há»¯u", "hello", "mĂ y lĂ  ai", "giá»›i thiá»‡u Ä‘i", "cáº£m Æ¡n", "bye",
    "Ä‘á»“ chĂ³ cháº¿t", "ngÆ°Æ¡i ngu láº¯m", "ká»ƒ vá» linh Ä‘an", "lĂ m sao phi thÄƒng",
    "bĂ­ kĂ­p luyá»‡n kiáº¿m", "hahahaha", ":D", "ok Ä‘áº¡i ca"
]

def clear(): os.system('cls' if os.name == 'nt' else 'clear')

def send(msg: str):
    try:
        r = requests.post(URL, data={"message": msg}, timeout=TIMEOUT)
        if r.status_code == 200:
            reply = r.json().get("response", "...")
            print(f"{G}   Bot: {reply}{W}\n")
        else:
            print(f"{R}   Lá»—i {r.status_code}: {r.text}{W}\n")
    except requests.exceptions.ConnectionError:
        print(f"{R}   KhĂ´ng káº¿t ná»‘i Ä‘Æ°á»£c! Cháº¡y uvicorn config.asgi:app --reload chÆ°a Ä‘áº¡o há»¯u?{W}\n")
    except requests.exceptions.Timeout:
        print(f"{Y}   Bot Ä‘ang Ä‘á»™ kiáº¿p... nghÄ© quĂ¡ lĂ¢u rá»“i!{W}\n")
    except Exception as e:
        print(f"{R}   Lá»—i: {e}{W}\n")

def interactive():
    print(f"{B}=== CHáº¾ Äá»˜ CHAT TAY â€“ gĂµ 'thoat' Ä‘á»ƒ thoĂ¡t ==={W}\n")
    while True:
        try:
            msg = input(f"{Y}[Báº¡n]: {W}").strip()
            if msg.lower() in {"thoat", "exit", "quit", "bye"}:
                print(f"{G}\nPhi thÄƒng thĂ nh cĂ´ng, háº¹n gáº·p láº¡i trĂªn tiĂªn giá»›i!{W}\n")
                break
            if not msg: continue
            print()
            send(msg)
        except KeyboardInterrupt:
            print(f"\n\n{G}ThoĂ¡t Ä‘á»™t ngá»™t, coi chá»«ng tĂ¢m ma nháº­p!{W}\n")
            break

def auto():
    print(f"{B}=== AUTO TEST 14 CĂ‚U TU TIĂN ==={W}\n")
    for i, msg in enumerate(TEST_MESSAGES, 1):
        print(f"{Y}{i:02d}. [Báº¡n]: {msg}{W}")
        send(msg)
        time.sleep(1.8)
    print(f"{G}=== TEST XONG â€“ PHI THÄ‚NG HOĂ€N Táº¤T! ==={W}\n")

# ==================== MAIN ====================
if __name__ == "__main__":
    clear()
    print(f"{B}{'='*56}")
    print("       TOOL TEST CHAT TU TIĂN 2025 â€“ CMD EDITION")
    print("="*56 + f"{W}\n")

    choice = input(f"{B}Chá»n: {W}1 (auto test) | {W}2 (chat tay){B} â†’ ").strip() or "2"

    if choice == "1":
        auto()
    else:
        interactive()

    input(f"{Y}Nháº¥n Enter Ä‘á»ƒ thoĂ¡t...{W}")
    
    
    



    """_Luá»“ng xá»­ lĂ½ cĂ¢u há»i cá»§a user 

User gá»­i cĂ¢u â†’ chia nhá» thĂ nh chunks â†’ LLM láº¥y keyword â†’ chuyá»ƒn thĂ nh vector â†’ Ä‘Æ°a vĂ o mĂ´ hĂ¬nh â†’ xá»­ lĂ½ â†’ tráº£ vá» vector â†’ chuyá»ƒn thĂ nh ngĂ´n ngá»¯ tá»± nhiĂªn â†’ tráº£ user.

Ă 6 pháº§n 2 â€“ Ingest file

File.md Ä‘Æ°á»£c lÆ°u vĂ o botconfig.db.

LLM gom cĂ¢u cĂ¹ng 1 Ă½ â†’ chia thĂ nh chunks â†’ láº¥y keyword â†’ embed thĂ nh vector â†’ lÆ°u vectorstore/chroma.db.

Metadata (title, level, source, word_count)

title: tĂªn heading chunk â†’ hiá»ƒn thá»‹, phĂ¢n loáº¡i.

level: cáº¥p heading â†’ sáº¯p xáº¿p, Æ°u tiĂªn context quan trá»ng.

source: file gá»‘c â†’ filter khi nháº¯c file cá»¥ thá»ƒ.

word_count: sá»‘ tá»« â†’ preview, thá»‘ng kĂª, cĂ¢n nháº¯c quan trá»ng.

Luá»“ng dĂ¹ng metadata

Upload â†’ chunk + metadata.

Query â†’ filter/Æ°u tiĂªn chunk dá»±a trĂªn source, title, level; dĂ¹ng word_count Ä‘á»ƒ preview.

Quáº£n lĂ½ vector â†’ nhĂ³m theo file (source), sáº¯p xáº¿p theo level, hiá»ƒn thá»‹ preview (word_count).
    """
