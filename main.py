import requests
import json
import re
import time
from datetime import datetime, timedelta
import pytz

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
BOT_TOKEN = "5482422004:AAEKX1vcjzGbCYFrRL1MqKj4VymTGYwN7-c"
CHAT_ID = "-1003477065559" 

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
messages = {}          # {game_id: msg_id}
game_cache = {}        # {game_id: fixed_game_number}

SUITS_NAMES = {0: "♠", 1: "♣", 2: "♦", 3: "♥"}
RANKS = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://1xlite-79365.pro/ru/live/twentyone",
    "Cookie": "platform_type=desktop; SESSION=ca67837679e0e6d35d1b1baf235c2dff; lng=ru; _ga=GA1.1.185468893.1785072152"
}

# =====================================================================
# ФУНКЦИИ КАРТ
# =====================================================================
def get_game_number():
    now = datetime.now(MOSCOW_TZ)
    start = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now < start:
        start = start - timedelta(days=1)
    diff_minutes = (now - start).total_seconds() / 60
    game_number = int(diff_minutes) % 1440 + 1
    return game_number

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

# =====================================================================
# ОТПРАВКА В TELEGRAM
# =====================================================================
def send_message(text):
    try:
        r = requests.post(API + "/sendMessage", json={"chat_id": CHAT_ID, "text": text})
        if r.status_code == 200:
            return r.json()["result"]["message_id"]
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
    return None

def edit_message(message_id, text):
    try:
        url = f"{API}/editMessageText"
        payload = {"chat_id": CHAT_ID, "message_id": message_id, "text": text}
        r = requests.post(url, json=payload)
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка редактирования: {e}")
        return False

# =====================================================================
# ПОЛУЧЕНИЕ ДАННЫХ
# =====================================================================
def get_all_game_ids():
    try:
        lobby_url = "https://1xlite-79365.pro/ru/live/twentyone"
        response = requests.get(lobby_url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return []
        pattern = r'/twentyone/(\d+)'
        matches = re.findall(pattern, response.text)
        return list(set(matches)) if matches else []
    except Exception as e:
        print(f"❌ Ошибка лобби: {e}")
        return []

def get_game_data(game_id):
    url = f"https://1xlite-79365.pro/service-api/LiveFeed/GetGameZip?id={game_id}&isSubGames=true&GroupEvents=true&countevents=250&grMode=4&partner=7&topGroups=&country=190&marketType=1&isNewBuilder=true"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Ошибка получения игры {game_id}: {e}")
    return None

# =====================================================================
# ФОРМИРОВАНИЕ СООБЩЕНИЯ
# =====================================================================
def build_message(game_num, player_cards, dealer_cards, p_score, d_score, state):
    p_hand = format_cards(player_cards)
    d_hand = format_cards(dealer_cards)
    total = p_score + d_score if dealer_cards else p_score
    
    # Проверяем завершена ли игра
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

# =====================================================================
# ГЛАВНЫЙ ЦИКЛ
# =====================================================================
def parse_all_tables():
    global messages, game_cache
    
    game_ids = get_all_game_ids()
    if not game_ids:
        print("⚠️ Нет активных игр")
        return
    
    # Удаляем старые столы
    for old_id in list(messages.keys()):
        if old_id not in game_ids:
            del messages[old_id]
            if old_id in game_cache:
                del game_cache[old_id]
    
    for game_id in game_ids:
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
            continue
        
        # Фиксируем номер игры
        if game_id not in game_cache:
            game_cache[game_id] = get_game_number()
        
        game_num = game_cache[game_id]
        
        p_score = calculate_score(player_cards)
        d_score = calculate_score(dealer_cards) if dealer_cards else 0
        
        msg = build_message(game_num, player_cards, dealer_cards, p_score, d_score, state)
        
        if game_id in messages:
            edit_message(messages[game_id], msg)
        else:
            msg_id = send_message(msg)
            if msg_id:
                messages[game_id] = msg_id
        
        time.sleep(0.2)

# =====================================================================
# ЗАПУСК
# =====================================================================
if __name__ == "__main__":
    print("🃏 ПАРСЕР 21 ОЧКО (ВСЕ СТОЛЫ)")
    print(f"📊 Отправляет в: {CHAT_ID}")
    print("🔄 Обновление каждые 30 секунд")
    print("=" * 50)
    
    while True:
        try:
            parse_all_tables()
            time.sleep(30)
        except KeyboardInterrupt:
            print("\n🛑 Остановлен пользователем")
            break
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(5)