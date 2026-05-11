import os
import json
import urllib.request
import urllib.parse

BOT_TOKEN = "8758473045:AAHlHYIBYWIwBR083uO5ZLbVzq4ENQpbT9w"
# Statistika
stats = {
    "users": set(),
    "total_questions": 0,
    "today_questions": 0,
    "today_date": ""
}
ADMIN_ID = None  # Birinchi /start bosgan odam admin bo'ladi

GEMINI_KEYS = [
    "AIzaSyCHxGRuDSA35GPgxS7gbYMzhdpD1z1E9sY",
    "AIzaSyDMiAQ1Iw61KuFhI013cebvfgJEITMiZkY",
    "AIzaSyDUBr_f01-iYLVQnpKgtS2euXuYllK_RjQ",
    "AIzaSyC72LqvyxQ2ot2aotGtHaQruzvLLQijnZA",
    "AIzaSyCm6Jgzx5OrVS7AjP7GAtztp9QDduieyO0",
    "AIzaSyA0pjrT8sY0GJnYfW9Hq_tb65RA1rFFGEA",
    "AIzaSyDdg7EfUOKGeuWyFfpRj5d2pzPncMma9dE",
    "AIzaSyDvNffraHRAELYDA_DXK6AevWHvd0qKSak",
    "AIzaSyA7ovEbbx2qsT2rmLspByef_uyjJP8z85k"
]
current_key = 0

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

def telegram_request(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if data:
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def gemini_ask(question):
    global current_key
    prompt = SYSTEM_PROMPT + f"\n\nSavol: {question}"
    data = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048}
    }).encode()
    
    for i in range(len(GEMINI_KEYS)):
        key = GEMINI_KEYS[current_key % len(GEMINI_KEYS)]
        try:
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={key}",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            if "429" in str(e):
                current_key += 1
                import time
                time.sleep(2)
                continue
            raise e
    raise Exception("Serverga yuklanish ko\'p. 1 daqiqa kutib qayta yuboring.")

def send_message(chat_id, text, parse_mode=None):
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        telegram_request("sendMessage", data)
    except:
        # If markdown fails, send plain
        telegram_request("sendMessage", {"chat_id": chat_id, "text": text})

def send_typing(chat_id):
    telegram_request("sendChatAction", {"chat_id": chat_id, "action": "typing"})

offset = 0

print("OzbekHuquq_bot ishga tushdi!")

while True:
    try:
        result = telegram_request("getUpdates", {"offset": offset, "timeout": 30, "limit": 10})
        updates = result.get("result", [])
        
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")
            
            if not chat_id or not text:
                continue
            
            if text == "/start":
                stats["users"].add(str(chat_id))
                if ADMIN_ID is None:
                    ADMIN_ID = chat_id
                welcome = """⚖️ Huquq AI botiga xush kelibsiz!

Men O'zbekiston qonunchiligi bo'yicha yuridik maslahat beraman.

📝 Huquqiy savolingizni yozing — javob beraman!

Misol savollar:
• Qarz qaytarilmasa nima qilish kerak?
• Ishdan noqonuniy bo'shatilsa nima qilish kerak?
• Ajrashishda mulk qanday bo'linadi?

🌐 Sayt: https://huquq-ai.netlify.app"""
                send_message(chat_id, welcome)
                
            elif text == "/help":
                help_text = """📚 Yordam

Har qanday huquqiy savol yozing, men javob beraman.

Kategoriyalar:
⚖️ Mehnat huquqi
👨‍👩‍👧 Oila huquqi  
🏠 Mulk huquqi
🚔 Jinoyat huquqi
💼 Tadbirkorlik huquqi
🌾 Yer huquqi
💰 Soliq huquqi
📜 Meros huquqi

/start — Boshlaish
/help — Yordam"""
                send_message(chat_id, help_text)
                
            elif text.startswith("/"):
                send_message(chat_id, "Noma'lum buyruq. /help ni bosing.")
                
            elif text == "/stats":
                if str(chat_id) == str(ADMIN_ID):
                    import datetime
                    msg = f"""📊 Statistika:

👥 Jami foydalanuvchilar: {len(stats['users'])}
❓ Jami savollar: {stats['total_questions']}
📅 Bugun savollar: {stats['today_questions']}"""
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Bu buyruq faqat admin uchun.")

            else:
                # Track stats
                import datetime
                today = datetime.date.today().isoformat()
                if stats["today_date"] != today:
                    stats["today_date"] = today
                    stats["today_questions"] = 0
                stats["users"].add(str(chat_id))
                stats["total_questions"] += 1
                stats["today_questions"] += 1

                send_typing(chat_id)
                send_message(chat_id, "⚖️ Javob tayyorlanmoqda... Iltimos kuting (10-20 soniya)")
                
                try:
                    answer = gemini_ask(text)
                    send_message(chat_id, answer)
                except Exception as e:
                    send_message(chat_id, f"❌ Xato yuz berdi: {str(e)}\n\nIltimos qayta urinib ko'ring.")
                    
    except KeyboardInterrupt:
        print("Bot to'xtatildi.")
        break
    except Exception as e:
        print(f"Xato: {e}")
        import time
        time.sleep(5)
