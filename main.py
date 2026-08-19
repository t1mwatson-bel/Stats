import requests
import json
import re
import time
from datetime import datetime, timedelta
import pytz
import sys

# =====================================================================
# ПРИНУДИТЕЛЬНЫЙ ВЫВОД ЛОГОВ
# =====================================================================
sys.stdout.flush()
print("=" * 60, flush=True)
print("🃏 ПАРСЕР 21 ОЧКО (ВСЕ СТОЛЫ) - ЗАПУСК", flush=True)
print("=" * 60, flush=True)

# =====================================================================
# ТЕСТ ДОСТУПА К API
# =====================================================================
print("🧪 Тест доступа к API...", flush=True)
try:
    r = requests.get("https://1xlite-84484.pro", timeout=10)
    print(f"📡 Статус (сайт): {r.status_code}", flush=True)
except Exception as e:
    print(f"❌ Ошибка доступа к сайту: {e}", flush=True)

# Тест API 21 очка
print("🧪 Тест API 21 очка...", flush=True)
test_url = "https://1xlite-84484.pro/service-api/LiveFeed/Get1x2_VZip?sports=146&champs=1643503&count=10&gr=2336&mode=4&country=190&getEmpty=true&virtualSports=true&noFilterBlockEvent=true"
try:
    r = requests.get(test_url, timeout=10)
    print(f"📡 Статус API: {r.status_code}", flush=True)
    if r.status_code == 200:
        data = r.json()
        print(f"📊 Ключи: {data.keys() if data else 'нет данных'}", flush=True)
        print(f"📊 Value: {len(data.get('Value', []))} объектов", flush=True)
    else:
        print(f"⚠️ Ответ: {r.text[:200] if r.text else 'пусто'}", flush=True)
except Exception as e:
    print(f"❌ Ошибка API: {e}", flush=True)
# =====================================================================

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
BOT_TOKEN = "5482422004:AAEKX1vcjzGbCYFrRL1MqKj4VymTGYwN7-c"
CHAT_ID = "-1003477065559"

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
messages = {}
game_cache = {}

SUITS_NAMES = {0: "♠", 1: "♣", 2: "♦", 3: "♥"}
RANKS = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://1xlite-84484.pro/ru/live/twentyone",
    "Cookie": "platform_type=desktop; SESSION=ca67837679e0e6d35d1b1baf235c2dff; lng=ru; _ga=GA1.1.185468893.1785072152"
}

print("✅ Настройки загружены", flush=True)

# =====================================================================
# ФУНКЦИИ
# =====================================================================
def get_game_number():
    now = datetime.now(MOSCOW_TZ)
    start = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now < start:
        start = start - timedelta(days=1)
    diff_minutes = (now - start).total_seconds() / 60
    return int(diff_minutes) % 1440 + 1

def get_all_game_ids():
    try:
        url = "https://1xlite-84484.pro/service-api/LiveFeed/Get1x2_VZip?sports=146&champs=1643503&count=40&gr=2336&mode=4&country=190&getEmpty=true&virtualSports=true&noFilterBlockEvent=true"
        print(f"🔍 Запрос к API: {url[:80]}...", flush=True)
        response = requests.get(url, headers=HEADERS, timeout=10)
        print(f"📡 Статус API (игры): {response.status_code}", flush=True)
        if response.status_code != 200:
            return []
        data = response.json()
        games = data.get("Value", [])
        print(f"🔍 Найдено игр в ответе: {len(games)}", flush=True)
        ids = []
        for game in games:
            if game.get("I"):
                ids.append(str(game.get("I")))
            elif game.get("DI"):
                ids.append(str(game.get("DI")))
        print(f"🔍 Извлечено ID: {len(ids)}", flush=True)
        return ids
    except Exception as e:
        print(f"❌ Ошибка получения ID: {e}", flush=True)
        return []

def get_game_data(game_id):
    url = f"https://1xlite-84484.pro/service-api/LiveFeed/GetGameZip?id={game_id}&isSubGames=true&GroupEvents=true&countevents=250&grMode=4&partner=7&topGroups=&country=190&marketType=1&isNewBuilder=true"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Статус игры {game_id}: {response.status_code}", flush=True)
    except Exception as e:
        print(f"❌ Ошибка игры {game_id}: {e}", flush=True)
    return None

def format_cards(cards):
    if not cards:
        return ""
    result = []
    for c in cards:
        suit = SUITS_NAMES.get(c.get("CS", 0), "?")
        rank = RANKS.get(c.get("CV", 0), str(c.get("CV", "?")))
        result.append(f"{rank}{suit}")
    return "".join(result)

def calculate_score(cards):
    if not cards:
        return 0
    score = 0
    aces = 0
    for c in cards:
        cv = c.get("CV", 0)
        if cv == 14:
            aces += 1
            score += 11
        elif cv == 13:
            score += 4
        elif cv == 12:
            score += 3
        elif cv == 11:
            score += 2
        elif 6 <= cv <= 10:
            score += cv
    while score > 21 and aces > 0:
        score -= 10
        aces -= 1
    return score

def build_message(game_num, player_cards, dealer_cards, p_score, d_score, state):
    p_hand = format_cards(player_cards)
    d_hand = format_cards(dealer_cards)
    total = p_score + d_score if dealer_cards else p_score
    
    is_finished = False
    if p_score == 21 or d_score == 21:
        is_finished = True
    if p_score > 21 or d_score > 21:
        is_finished = True
    if state in ["4", "5"]:
        is_finished = True
    
    if not is_finished:
        if not dealer_cards:
            arrow = "◀️"
        else:
            arrow = "▶️"
        return f"#N{game_num}. {p_score}({p_hand}) {arrow} {d_score}({d_hand}) #T{total}"
    
    if p_score > 21:
        return f"#N{game_num}. {p_score}({p_hand}) - ✅{d_score}({d_hand}) #T{total}"
    if d_score > 21:
        return f"#N{game_num}. ✅{p_score}({p_hand}) - {d_score}({d_hand}) #T{total}"
    if p_score > d_score:
        return f"#N{game_num}. ✅{p_score}({p_hand}) - {d_score}({d_hand}) #T{total}"
    if d_score > p_score:
        return f"#N{game_num}. {p_score}({p_hand}) - ✅{d_score}({d_hand}) #T{total}"
    return f"#N{game_num}. {p_score}({p_hand}) - 🔰{d_score}({d_hand}) #T{total}"

def send_message(text):
    try:
        r = requests.post(API + "/sendMessage", json={"chat_id": CHAT_ID, "text": text})
        if r.status_code == 200:
            return r.json()["result"]["message_id"]
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}", flush=True)
    return None

def edit_message(message_id, text):
    try:
        url = f"{API}/editMessageText"
        payload = {"chat_id": CHAT_ID, "message_id": message_id, "text": text}
        r = requests.post(url, json=payload)
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка редактирования: {e}", flush=True)
        return False

# =====================================================================
# ГЛАВНЫЙ ЦИКЛ
# =====================================================================
def parse_all_tables():
    global messages, game_cache
    
    print("🔄 Начинаю парсинг всех столов...", flush=True)
    
    game_ids = get_all_game_ids()
    if not game_ids:
        print("⚠️ Нет активных игр или ошибка получения ID", flush=True)
        return
    
    print(f"🔍 Найдено столов: {len(game_ids)}", flush=True)
    
    for game_id in game_ids:
        print(f"📊 Обработка стола: {game_id}", flush=True)
        data = get_game_data(game_id)
        if not data:
            continue
        
        value = data.get("Value", {})
        sc = value.get("SC", {})
        
        player_cards = []
        dealer_cards = []
        state = None
        
        for item in sc.get("S", []):
            if item.get("Key") == "P1":
                player_cards = json.loads(item.get("Value", "[]"))
            if item.get("Key") == "P2":
                dealer_cards = json.loads(item.get("Value", "[]"))
            if item.get("Key") == "STATE":
                state = item.get("Value")
        
        if not player_cards:
            print(f"⏭️ Нет карт игрока в {game_id}", flush=True)
            continue
        
        if game_id not in game_cache:
            game_cache[game_id] = get_game_number()
        
        game_num = game_cache[game_id]
        
        p_score = calculate_score(player_cards)
        d_score = calculate_score(dealer_cards) if dealer_cards else 0
        
        msg = build_message(game_num, player_cards, dealer_cards, p_score, d_score, state)
        print(f"📤 {msg}", flush=True)
        
        if game_id in messages:
            edit_message(messages[game_id], msg)
        else:
            msg_id = send_message(msg)
            if msg_id:
                messages[game_id] = msg_id
        
        time.sleep(0.3)

# =====================================================================
# ЗАПУСК
# =====================================================================
if __name__ == "__main__":
    print("🔄 Основной цикл запущен", flush=True)
    
    while True:
        try:
            parse_all_tables()
            print("💤 Ожидание 30 секунд...", flush=True)
            time.sleep(30)
        except KeyboardInterrupt:
            print("\n🛑 Остановлен пользователем", flush=True)
            break
        except Exception as e:
            print(f"❌ Ошибка: {e}", flush=True)
            time.sleep(5)