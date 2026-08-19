import os
import sys
import requests
import json
import time
import re
from datetime import datetime, timedelta
import pytz

# =====================================================================
# ПРИНУДИТЕЛЬНЫЙ ВЫВОД ЛОГОВ
# =====================================================================
sys.stdout.flush()
print("=" * 60, flush=True)
print("🃏 ПАРСЕР 21 ОЧКО - ЗАПУСК", flush=True)
print("=" * 60, flush=True)

# =====================================================================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (НАСТРАИВАЮТСЯ НА ХОСТИНГЕ)
# =====================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN_21') or "ТВОЙ_ТОКЕН_БОТА"
CHAT_ID = os.getenv('CHAT_ID_21') or "ID_КАНАЛА_ИЛИ_ЧАТА"

if not BOT_TOKEN or not CHAT_ID:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN_21 или CHAT_ID_21 не заданы!", flush=True)
    exit(1)

print(f"✅ BOT_TOKEN: {BOT_TOKEN[:5] if BOT_TOKEN else 'НЕ НАЙДЕН'}...", flush=True)
print(f"✅ CHAT_ID: {CHAT_ID if CHAT_ID else 'НЕ НАЙДЕН'}", flush=True)

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://1xlite-84484.pro/ru/live/twentyone",
    "Cookie": "platform_type=desktop; SESSION=ca67837679e0e6d35d1b1baf235c2dff; lng=ru; _ga=GA1.1.185468893.1785072152"
}

# =====================================================================
# ОСНОВНЫЕ ФУНКЦИИ
# =====================================================================
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get("result", {}).get("message_id")
        return None
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}", flush=True)
        return None

def edit_telegram(message_id, message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
        payload = {"chat_id": CHAT_ID, "message_id": message_id, "text": message, "parse_mode": "HTML"}
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка редактирования: {e}", flush=True)
        return False

def get_game_number():
    now = datetime.now(MOSCOW_TZ)
    start = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now < start:
        start = start - timedelta(days=1)
    diff_minutes = (now - start).total_seconds() / 60
    game_number = int(diff_minutes / 2) % 720 + 1
    return game_number

def get_active_game_id():
    try:
        lobby_url = "https://1xlite-84484.pro/ru/live/twentyone"
        response = requests.get(lobby_url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            pattern = r'/twentyone/(\d+)'
            match = re.search(pattern, response.text)
            if match:
                game_id = match.group(1)
                print(f"✅ Найден активный ID игры: {game_id}", flush=True)
                return game_id
            else:
                print("⚠️ ID игры не найден на странице", flush=True)
                print(response.text[:500], flush=True)
    except Exception as e:
        print(f"❌ Ошибка получения ID игры: {e}", flush=True)
    return None

def get_cards(value_str):
    if not value_str or value_str == "[]":
        return []
    try:
        cards = json.loads(value_str)
        result = []
        suit_map = {0: '♠', 1: '♣', 2: '♦', 3: '♥'}
        rank_map = {'1': '10', '6': '6', '7': '7', '8': '8', '9': '9', '10': '10', '11': 'J', '12': 'Q', '13': 'K', '14': 'A'}
        for card in cards:
            cs = card.get('CS', '?')
            cv = card.get('CV', '?')
            cv_str = str(cv)
            rank = rank_map.get(cv_str, str(cv))
            suit = suit_map.get(cs, '')
            if rank and suit:
                card_str = f"{rank}{suit}"
                if card_str not in result:
                    result.append(card_str)
        return result
    except Exception as e:
        print(f"❌ Ошибка парсинга карт: {e}", flush=True)
        return []

def calculate_score(cards):
    score = 0
    for card in cards:
        if not card:
            continue
        rank = card[0]
        if rank == '6':
            score += 6
        elif rank == '7':
            score += 7
        elif rank == '8':
            score += 8
        elif rank == '9':
            score += 9
        elif rank == '10':
            score += 10
        elif rank == 'J':
            score += 2
        elif rank == 'Q':
            score += 3
        elif rank == 'K':
            score += 4
        elif rank == 'A':
            score += 11
    return score

def format_hand(cards):
    cards = cards[::-1]
    result = []
    for card in cards:
        rank = card[0]
        suit = card[-1]
        if suit in ['♥', '♦']:
            result.append(f"<b style='color:red;'>{rank}{suit}</b>")
        else:
            result.append(f"<b>{rank}{suit}</b>")
    return ''.join(result)

def wait_for_start():
    while True:
        now = datetime.now(MOSCOW_TZ)
        if now.second == 58 and now.minute % 2 == 1:
            return time.time()
        time.sleep(0.1)

def get_close_time():
    now = datetime.now(MOSCOW_TZ)
    if now.minute % 2 == 1 and now.second >= 52:
        close = now.replace(minute=now.minute + 2, second=52, microsecond=0)
    elif now.minute % 2 == 1:
        close = now.replace(second=52, microsecond=0)
    else:
        close = now.replace(minute=now.minute + 1, second=52, microsecond=0)
    return close.timestamp()

# =====================================================================
# ОСНОВНОЙ ЦИКЛ
# =====================================================================
def main():
    print("🔄 ПАРСЕР ЗАПУЩЕН, ОЖИДАНИЕ СТАРТА...", flush=True)
    processed_games = set()
    
    while True:
        try:
            start_time = wait_for_start()
            print(f"🕐 Старт в {datetime.fromtimestamp(start_time).strftime('%H:%M:%S')}", flush=True)
            
            close_time = get_close_time()
            print(f"🕐 Закрытие в {datetime.fromtimestamp(close_time).strftime('%H:%M:%S')}", flush=True)
            
            time.sleep(2)
            
            game_id = None
            print("🔍 Поиск игры...", flush=True)
            for _ in range(10):
                any_id = get_active_game_id()
                if any_id:
                    if any_id not in processed_games:
                        game_id = any_id
                        processed_games.add(game_id)
                        print(f"✅ Найдена игра: {game_id}", flush=True)
                        break
                    else:
                        print(f"⏭️ Игра {any_id} уже обработана", flush=True)
                time.sleep(0.5)
            
            if not game_id:
                print("❌ Игра не найдена, перезапуск...", flush=True)
                continue
            
            url = f"https://1xlite-84484.pro/service-api/LiveFeed/GetGameZip?id={game_id}&isSubGames=true&GroupEvents=true&countevents=250&grMode=4&partner=7&topGroups=&country=190&marketType=1&isNewBuilder=true"
            
            game_started = False
            last_message_id = None
            last_player_cards = ""
            last_dealer_cards = ""
            game_number = 0
            
            while time.time() < close_time:
                try:
                    response = requests.get(url, headers=HEADERS, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        sc = data.get("Value", {}).get("SC", {})
                        
                        player_cards = []
                        dealer_cards = []
                        for item in sc.get("S", []):
                            if item.get("Key") == "P1":
                                player_cards = get_cards(item.get("Value", "[]"))
                            if item.get("Key") == "P2":
                                dealer_cards = get_cards(item.get("Value", "[]"))
                        
                        if player_cards:
                            player_cards_reversed = player_cards[::-1]
                            dealer_cards_reversed = dealer_cards[::-1] if dealer_cards else []
                            
                            player_str_cards = ','.join(player_cards_reversed)
                            dealer_str_cards = ','.join(dealer_cards_reversed)
                            
                            cards_changed = (
                                player_str_cards != last_player_cards or 
                                dealer_str_cards != last_dealer_cards
                            )
                            
                            if not game_started:
                                game_started = True
                                game_number = get_game_number()
                                last_player_cards = player_str_cards
                                last_dealer_cards = dealer_str_cards
                                
                                player_score = calculate_score(player_cards_reversed)
                                dealer_score = calculate_score(dealer_cards_reversed) if dealer_cards_reversed else 0
                                player_str = f"{player_score}({format_hand(player_cards_reversed)})"
                                dealer_str = f"{dealer_score}({format_hand(dealer_cards_reversed)})" if dealer_cards_reversed else "0()"
                                total = player_score + dealer_score if dealer_cards_reversed else player_score
                                
                                turn = "⏱️" if len(dealer_cards_reversed) < len(player_cards_reversed) else "🎯"
                                
                                msg = f"#N{game_number} {turn}{player_str}-{dealer_str} #T{total}"
                                last_message_id = send_telegram(msg)
                                print(f"🎯 Старт: {msg}", flush=True)
                                continue
                            
                            if not cards_changed:
                                time.sleep(0.3)
                                continue
                            
                            last_player_cards = player_str_cards
                            last_dealer_cards = dealer_str_cards
                            
                            player_score = calculate_score(player_cards_reversed)
                            dealer_score = calculate_score(dealer_cards_reversed) if dealer_cards_reversed else 0
                            player_str = f"{player_score}({format_hand(player_cards_reversed)})"
                            dealer_str = f"{dealer_score}({format_hand(dealer_cards_reversed)})" if dealer_cards_reversed else "0()"
                            total = player_score + dealer_score if dealer_cards_reversed else player_score
                            
                            turn = "⏱️" if len(dealer_cards_reversed) < len(player_cards_reversed) else "🎯"
                            
                            msg = f"#N{game_number} {turn}{player_str}-{dealer_str} #T{total}"
                            if last_message_id:
                                edit_telegram(last_message_id, msg)
                            else:
                                last_message_id = send_telegram(msg)
                            print(f"🔄 {msg}", flush=True)
                    
                    time.sleep(0.3)
                    
                except requests.exceptions.Timeout:
                    print("⏱️ Таймаут запроса, продолжаем...", flush=True)
                    continue
                except Exception as e:
                    print(f"❌ Сбой: {e}", flush=True)
                    time.sleep(3)
                    break
            
            print("⏰ Время работы истекло, перезапуск...", flush=True)
            
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()