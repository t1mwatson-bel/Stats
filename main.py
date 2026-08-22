import requests
import json
import time
import os
import re
from datetime import datetime, timedelta
import pytz

# =====================================================================
# ЧАСОВОЙ ПОЯС (МОСКВА)
# =====================================================================
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

if not BOT_TOKEN or not CHANNEL_ID:
    print("❌ Ошибка: BOT_TOKEN или CHANNEL_ID не заданы!", flush=True)
    exit(1)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://melbet-38497.pro/",
}

# Список игр Баккара
LIST_URL = "https://melbet-38497.pro/service-api/LiveFeed/Get1x2_VZip?sports=236&champs=2050671&count=40&gr=1521&mode=4&country=192&partner=8&getEmpty=true&virtualSports=true&noFilterBlockEvent=true"
DETAIL_URL_TEMPLATE = "https://melbet-38497.pro/service-api/LiveFeed/GetGameZip?id={game_id}&isSubGames=true&GroupEvents=true&countevents=250&grMode=4&partner=8&topGroups=&country=192&marketType=1&isNewBuilder=true"

SUITS = {
    0: "♠️",
    1: "♣️",
    2: "♦️",
    3: "♥️"
}

RANKS = {
    1: "A", 2: "2", 3: "3", 4: "4", 5: "5",
    6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "J", 12: "Q", 13: "K"
}

processed_games = set()
messages = {}

# =====================================================================
# ФУНКЦИИ
# =====================================================================
def get_game_number():
    """Номер игры от 1 до 1440 (каждую минуту, старт в 03:00)"""
    now = datetime.now(MOSCOW_TZ)
    start = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now < start:
        start = start - timedelta(days=1)
    diff_minutes = (now - start).total_seconds() / 60
    game_number = int(diff_minutes) % 1440 + 1
    return game_number

def get_active_games():
    """Получает список активных игр Баккара"""
    try:
        response = requests.get(LIST_URL, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            games = data.get("Value", [])
            
            active_games = []
            for game in games:
                game_id = game.get("I")
                if game_id and str(game_id) not in processed_games:
                    active_games.append(game)
            
            print(f"📊 Найдено активных игр: {len(active_games)}", flush=True)
            return active_games
        else:
            print(f"⚠️ Статус API: {response.status_code}", flush=True)
    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
    return []

def get_game_data(game_id):
    """Получает данные конкретной игры"""
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
    """Форматирует карты для вывода"""
    if not cards:
        return ""
    result = []
    for card in cards:
        suit = SUITS.get(card.get("S", 0), "?")
        rank = RANKS.get(card.get("R", 0), "?")
        result.append(f"{rank}{suit}")
    return "".join(result)

def calculate_score(cards):
    """Считает очки в баккара (последняя цифра суммы)"""
    if not cards:
        return 0
    
    score = 0
    for card in cards:
        rank = card.get("R", 0)
        if rank == 1:  # Туз = 1
            score += 1
        elif 2 <= rank <= 9:
            score += rank
        else:  # 10, J, Q, K = 0
            score += 0
    
    return score % 10  # Берём последнюю цифру

def is_game_finished(state):
    """Проверяет, завершена ли игра"""
    return state == "Игра завершена"

def build_message(game_num, player_cards, banker_cards, p_score, b_score):
    """Формирует сообщение для отправки"""
    p_hand = format_cards(player_cards)
    b_hand = format_cards(banker_cards)
    
    # Определяем результат
    if p_score > b_score:
        result = "✅"
    elif b_score > p_score:
        result = "❌"
    else:
        result = "🔰"
    
    return f"#N{game_num}. {p_score}({p_hand}) - {result}{b_score}({b_hand}) #T{p_score + b_score}"

def send_message(text):
    """Отправляет сообщение в Telegram"""
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
    """Редактирует сообщение в Telegram"""
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
                
                if game_id in processed_games:
                    continue
                
                data = get_game_data(game_id)
                if not data:
                    continue
                
                # Парсим карты игрока и банка
                sc = data.get("Value", {}).get("SC", {})
                fs = sc.get("FS", {})
                
                player_cards = []
                banker_cards = []
                state = sc.get("CPS", "")
                
                # Ищем карты игрока (P) и банка (B)
                for item in sc.get("S", []):
                    if item.get("Key") == "P":
                        player_cards = json.loads(item.get("Value", "[]"))
                    if item.get("Key") == "B":
                        banker_cards = json.loads(item.get("Value", "[]"))
                
                if not player_cards and not banker_cards:
                    continue
                
                game_number = get_game_number()
                
                p_score = calculate_score(player_cards) if player_cards else 0
                b_score = calculate_score(banker_cards) if banker_cards else 0
                
                msg = build_message(game_number, player_cards, banker_cards, p_score, b_score)
                
                if game_id in messages:
                    edit_message(messages[game_id], msg)
                    print(f"🔄 Обновлена игра {game_id}: {msg}", flush=True)
                else:
                    msg_id = send_message(msg)
                    if msg_id:
                        messages[game_id] = msg_id
                        print(f"📤 Новая игра {game_id}: {msg}", flush=True)
                
                if is_game_finished(state):
                    processed_games.add(game_id)
                    print(f"🏁 Игра {game_id} завершена", flush=True)
                
                time.sleep(0.3)
            
            # Очистка кэша
            if len(processed_games) > 200:
                processed_games.clear()
                print("🗑️ Кэш обработанных игр очищен", flush=True)
            
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()