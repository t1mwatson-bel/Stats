import os
import sys
import requests
import json
import re
import time
from datetime import datetime, timedelta
import pytz

# =====================================================================
# ПРИНУДИТЕЛЬНЫЙ ВЫВОД ЛОГОВ
# =====================================================================
sys.stdout.flush()
print("=" * 60, flush=True)
print("🃏 ПАРСЕР БАККАРА (ПРЯМОЙ ПАРСИНГ API)", flush=True)
print("=" * 60, flush=True)

# =====================================================================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (ТОЛЬКО 2!)
# =====================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

print("🔍 ДИАГНОСТИКА ПЕРЕМЕННЫХ:", flush=True)
print(f"BOT_TOKEN: {BOT_TOKEN[:5] if BOT_TOKEN else 'НЕ ЗАДАН'}", flush=True)
print(f"CHANNEL_ID: {CHANNEL_ID if CHANNEL_ID else 'НЕ ЗАДАН'}", flush=True)
print("=" * 60, flush=True)

if not BOT_TOKEN or not CHANNEL_ID:
    print("❌ ОШИБКА: BOT_TOKEN или CHANNEL_ID не заданы!", flush=True)
    exit(1)

print("✅ Все переменные заданы!", flush=True)

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
# ✅ Рабочее зеркало Melbet (поменяй, если не работает)
BASE_URL = "https://melbet-38497.pro"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE_URL}/ru/live/baccarat/",
}

# Список игр Баккара
LIST_URL = f"{BASE_URL}/service-api/LiveFeed/Get1x2_VZip?sports=236&champs=2050671&count=40&gr=1521&mode=4&country=192&partner=8&getEmpty=true&virtualSports=true&noFilterBlockEvent=true"
DETAIL_URL_TEMPLATE = f"{BASE_URL}/service-api/LiveFeed/GetGameZip?id={{game_id}}&isSubGames=true&GroupEvents=true&countevents=250&grMode=4&partner=8&topGroups=&country=192&marketType=1&isNewBuilder=true"

SUITS = {0: "♠️", 1: "♣️", 2: "♦️", 3: "♥️"}
RANKS = {1: "A", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K"}

PROCESSED_GAMES = set()
messages = {}

# =====================================================================
# ФУНКЦИИ
# =====================================================================
def get_game_number():
    now = datetime.now(pytz.timezone('Europe/Moscow'))
    start = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now < start:
        start = start - timedelta(days=1)
    diff_minutes = (now - start).total_seconds() / 60
    game_number = int(diff_minutes) % 1440 + 1
    return game_number

def get_active_games():
    try:
        response = requests.get(LIST_URL, headers=HEADERS, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "Value" in data:
                games = data.get("Value", [])
            elif isinstance(data, list):
                games = data
            else:
                return []
            
            active_games = []
            for game in games:
                game_id = game.get("I")
                if game_id and str(game_id) not in PROCESSED_GAMES:
                    active_games.append(game)
            
            return active_games
        else:
            print(f"⚠️ Статус API: {response.status_code}", flush=True)
    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
    
    return []

def get_game_data(game_id):
    try:
        url = DETAIL_URL_TEMPLATE.format(game_id=game_id)
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
        cs = c.get("CS", 0)
        cv = c.get("CV", 0)
        suit = SUITS.get(cs, "?")
        rank = RANKS.get(cv, str(cv))
        result.append(f"{rank}{suit}")
    return "".join(result)

def calculate_score(cards):
    if not cards:
        return 0
    
    score = 0
    for c in cards:
        cv = c.get("CV", 0)
        if cv == 1:       # Туз = 1
            score += 1
        elif 2 <= cv <= 9:
            score += cv
        else:              # 10, J, Q, K = 0
            score += 0
    
    return score % 10

def is_game_finished(state):
    return state in ["4", "5"]

def build_message(game_num, player_cards, dealer_cards, p_score, d_score):
    p_hand = format_cards(player_cards)
    d_hand = format_cards(dealer_cards)
    total = p_score + d_score
    
    if p_score > d_score:
        result = "✅"
    elif d_score > p_score:
        result = "❌"
    else:
        result = "🔰"
    
    return f"#N{game_num}. {p_score}({p_hand}) - {result}{d_score}({d_hand}) #T{total}"

def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHANNEL_ID, "text": text}
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return response.json()["result"]["message_id"]
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}", flush=True)
    return None

def edit_message(message_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
        payload = {"chat_id": CHANNEL_ID, "message_id": message_id, "text": text}
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка редактирования: {e}", flush=True)
        return False

# =====================================================================
# ОСНОВНОЙ ЦИКЛ
# =====================================================================
def main():
    print("🔄 ПАРСЕР БАККАРА ЗАПУЩЕН", flush=True)
    print(f"📢 Канал: {CHANNEL_ID}", flush=True)
    print(f"🌐 Зеркало: {BASE_URL}", flush=True)
    print("=" * 60, flush=True)
    
    while True:
        try:
            active_games = get_active_games()
            
            if not active_games:
                print("💤 Нет активных игр, ждём 5 секунд...", flush=True)
                time.sleep(5)
                continue
            
            for game in active_games:
                game_id = str(game.get("I"))
                
                if game_id in PROCESSED_GAMES:
                    continue
                
                data = get_game_data(game_id)
                if not data:
                    continue
                
                sc = data.get("Value", {}).get("SC", {})
                
                player_cards = []
                dealer_cards = []
                state = None
                
                for item in sc.get("S", []):
                    if item.get("Key") == "P":
                        try:
                            player_cards = json.loads(item.get("Value", "[]"))
                        except:
                            player_cards = []
                    if item.get("Key") == "B":
                        try:
                            dealer_cards = json.loads(item.get("Value", "[]"))
                        except:
                            dealer_cards = []
                    if item.get("Key") == "STATE":
                        state = item.get("Value")
                
                if not player_cards:
                    continue
                
                game_number = get_game_number()
                
                p_score = calculate_score(player_cards) if player_cards else 0
                d_score = calculate_score(dealer_cards) if dealer_cards else 0
                
                msg = build_message(game_number, player_cards, dealer_cards, p_score, d_score)
                
                if game_id in messages:
                    edit_message(messages[game_id], msg)
                    print(f"🔄 Обновлена игра {game_id}: {msg}", flush=True)
                else:
                    msg_id = send_message(msg)
                    if msg_id:
                        messages[game_id] = msg_id
                        print(f"📤 Новая игра {game_id}: {msg}", flush=True)
                
                if is_game_finished(state):
                    PROCESSED_GAMES.add(game_id)
                    print(f"🏁 Игра {game_id} завершена", flush=True)
                
                time.sleep(0.3)
            
            if len(PROCESSED_GAMES) > 200:
                PROCESSED_GAMES.clear()
                print("🗑️ Кэш обработанных игр очищен", flush=True)
            
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()