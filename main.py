import os
import json
import time
import datetime
import urllib.request
import urllib.error

# =============================================
# MUHIM: Quyidagi o'zgaruvchilarni environment
# variable orqali o'rnating, kodga yozmang!
# Masalan: export BOT_TOKEN="your_token_here"
# =============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

GEMINI_KEYS = [
    key.strip()
    for key in os.environ.get("GEMINI_KEYS", "").split(",")
    if key.strip()
]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable o'rnatilmagan!")
if not GEMINI_KEYS:
    raise ValueError("GEMINI_KEYS environment variable o'rnatilmagan!")

# =============================================
# Statistika (xotirada — bot qayta ishga tushsa
# yo'qoladi; doimiy saqlash uchun DB kerak)
# =============================================
stats = {
    "users": set(),
    "total_questions": 0,
    "today_questions": 0,
    "today_date": "",
}

current_key_index = 0

SYSTEM_PROMPT = """Sen O'zbekiston qonunchiligini biluvchi yuridik maslahatchi sun'iy intellektsiz. Savollarga quyidagi formatda to'liq javob ber:

VAZIYAT: [2 gap]

QONUN: [qonun nomi va yili]

1-MODDA:
Modda raqami va nomi: [...]
Modda matni: [...]
Izohi: [...]

2-MODDA:
Modda raqami va nomi: [...]
Modda matni: [...]
Izohi: [...]

JAVOBGARLIK: [...]

NIMA QILISH KERAK:
Qadam 1: [...]
Qadam 2: [...]
Qadam 3: [...]

Muhim: Javobni to'liq yoz, hech qachon yarim qoldirma!"""


# =============================================
# Yordamchi funksiyalar
# =============================================

def telegram_request(method, data=None):
    """Telegram API ga so'rov yuboradi."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def send_message(chat_id, text, parse_mode=None):
    """Foydalanuvchiga xabar yuboradi. Markdown ishlamasa — oddiy matn yuboradi."""
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        telegram_request("sendMessage", data)
    except Exception:
        # Markdown sintaksis xatosi bo'lsa, parse_mode siz qayta urinib ko'ramiz
        try:
            telegram_request("sendMessage", {"chat_id": chat_id, "text": text})
        except Exception as e:
            print(f"Xabar yuborib bo'lmadi (chat_id={chat_id}): {e}")


def send_typing(chat_id):
    """'Yozmoqda...' holatini ko'rsatadi."""
    try:
        telegram_request("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


def update_daily_stats():
    """Kunlik statistikani yangilaydi."""
    today = datetime.date.today().isoformat()
    if stats["today_date"] != today:
        stats["today_date"] = today
        stats["today_questions"] = 0


def gemini_ask(question):
    """
    Gemini API dan javob oladi.
    Agar joriy kalit 429 qaytarsa, keyingi kalitga o'tadi.
    """
    global current_key_index

    prompt = SYSTEM_PROMPT + f"\n\nSavol: {question}"
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }).encode()

    for attempt in range(len(GEMINI_KEYS)):
        key = GEMINI_KEYS[current_key_index % len(GEMINI_KEYS)]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.0-flash:generateContent?key={key}"
        )
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                return result["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            print(f"Gemini kalit #{current_key_index % len(GEMINI_KEYS)} xato {e.code}: {error_body[:200]}")
            if e.code in (429, 500, 503):
                # Limit yoki server xatosi — keyingi kalitga o'tamiz
                current_key_index += 1
                time.sleep(3)
                continue
            raise RuntimeError(f"Gemini API xato ({e.code}): {e.reason}") from e
        except urllib.error.URLError as e:
            print(f"Tarmoq xatosi: {e.reason}")
            time.sleep(3)
            continue
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Gemini javobini o'qib bo'lmadi: {e}") from e

    # Barcha kalitlar limitga yetdi — 60 soniya kutib qayta urinamiz
    print("Barcha kalitlar limitga yetdi. 60 soniya kutilmoqda...")
    time.sleep(60)
    current_key_index = 0

    key = GEMINI_KEYS[0]
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={key}"
    )
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        raise RuntimeError(
            "Serverga yuklanish juda ko'p. Bir oz vaqt o'tib qayta yuboring."
        ) from e


# =============================================
# Xabarlarni qayta ishlash
# =============================================

def handle_message(message):
    """Kelgan xabarni qayta ishlaydi."""
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return

    # Foydalanuvchini ro'yxatga olamiz
    stats["users"].add(str(chat_id))

    if text == "/start":
        welcome = (
            "⚖️ Huquq AI botiga xush kelibsiz!\n\n"
            "Men O'zbekiston qonunchiligi bo'yicha yuridik maslahat beraman.\n\n"
            "📝 Huquqiy savolingizni yozing — javob beraman!\n\n"
            "Misol savollar:\n"
            "• Qarz qaytarilmasa nima qilish kerak?\n"
            "• Ishdan noqonuniy bo'shatilsa nima qilish kerak?\n"
            "• Ajrashishda mulk qanday bo'linadi?\n\n"
            "🌐 Sayt: https://huquq-ai.netlify.app"
        )
        send_message(chat_id, welcome)

    elif text == "/help":
        help_text = (
            "📚 Yordam\n\n"
            "Har qanday huquqiy savol yozing, men javob beraman.\n\n"
            "Kategoriyalar:\n"
            "⚖️ Mehnat huquqi\n"
            "👨‍👩‍👧 Oila huquqi\n"
            "🏠 Mulk huquqi\n"
            "🚔 Jinoyat huquqi\n"
            "💼 Tadbirkorlik huquqi\n"
            "🌾 Yer huquqi\n"
            "💰 Soliq huquqi\n"
            "📜 Meros huquqi\n\n"
            "/start — Boshlash\n"
            "/help — Yordam\n"
            "/myid — Telegram ID ni ko'rish"
        )
        send_message(chat_id, help_text)

    elif text == "/myid":
        send_message(chat_id, f"Sizning Telegram ID: {chat_id}")

    elif text == "/stats":
        if chat_id == ADMIN_ID:
            msg = (
                f"📊 Statistika:\n\n"
                f"👥 Jami foydalanuvchilar: {len(stats['users'])}\n"
                f"❓ Jami savollar: {stats['total_questions']}\n"
                f"📅 Bugun savollar: {stats['today_questions']}"
            )
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "❌ Bu buyruq faqat admin uchun.")

    elif text.startswith("/"):
        send_message(chat_id, "Noma'lum buyruq. /help ni bosing.")

    else:
        # Oddiy savol — Gemini ga yuboramiz
        update_daily_stats()
        stats["total_questions"] += 1
        stats["today_questions"] += 1

        send_typing(chat_id)
        send_message(chat_id, "⚖️ Javob tayyorlanmoqda... Iltimos kuting (10–20 soniya)")

        try:
            answer = gemini_ask(text)
            send_message(chat_id, answer)
        except Exception as e:
            send_message(
                chat_id,
                f"❌ Xato yuz berdi: {e}\n\nIltimos qayta urinib ko'ring.",
            )


# =============================================
# Asosiy tsikl
# =============================================

def main():
    offset = 0
    print("OzbekHuquq_bot ishga tushdi!")

    while True:
        try:
            result = telegram_request(
                "getUpdates",
                {"offset": offset, "timeout": 30, "limit": 10},
            )
            updates = result.get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                try:
                    handle_message(message)
                except Exception as e:
                    print(f"Xabarni qayta ishlashda xato: {e}")

        except KeyboardInterrupt:
            print("Bot to'xtatildi.")
            break
        except Exception as e:
            print(f"Asosiy tsiklda xato: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
