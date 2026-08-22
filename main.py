import os
import sys
import requests
import json
import re
import time
from datetime import datetime, timedelta
import pytz

# =====================================================================
# ЧАСОВОЙ ПОЯС (МОСКВА)
# =====================================================================
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# =====================================================================
# ПРИНУДИТЕЛЬНЫЙ ВЫВОД ЛОГОВ
# =====================================================================
sys.stdout.flush()
print("=" * 60, flush=True)
print("🃏 ПАРСЕР БАККАРА (ЛАЙВ)", flush=True)
print("=" * 60, flush=True)

# =====================================================================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# =====================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    BOT_TOKEN = os.getenv('BOT_TOKEN_PROGNOZ')

CHANNEL_STATS = os.getenv('CHANNEL_STATS_ID')
CHANNEL_PROGNOZ = os.getenv('CHANNEL_PROGNOZ_ID')

print("🔍 ДИАГНОСТИКА ПЕРЕМЕННЫХ:", flush=True)
print(f"BOT_TOKEN: {BOT_TOKEN[:5] if BOT_TOKEN else 'НЕ ЗАДАН'}", flush=True)
print(f"CHANNEL_STATS_ID: {CHANNEL_STATS if CHANNEL_STATS else 'НЕ ЗАДАН'}", flush=True)
print(f"CHANNEL_PROGNOZ_ID: {CHANNEL_PROGNOZ if CHANNEL_PROGNOZ else 'НЕ ЗАДАН'}", flush=True)
print("=" * 60, flush=True)

if not BOT_TOKEN or not CHANNEL_STATS or not CHANNEL_PROGNOZ:
    print("❌ ОШИБКА: переменные окружения не заданы!", flush=True)
    exit(1)

print("✅ Все переменные заданы!", flush=True)

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
OFFSET_FILE = "offset_baccarat.txt"
PROCESSED_GAMES = set()
messages = {}

# Масти для баккары
SUITS = {0: "♠️", 1: "♣️", 2: "♦️", 3: "♥️"}
RANKS = {
    1: "A", 2: "2", 3: "3", 4: "4", 5: "5",
    6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "J", 12: "Q", 13: "K"
}

# =====================================================================
# ФУНКЦИИ
# =====================================================================
def get_updates(offset):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"offset": offset, "timeout": 30}
    try:
        response = requests.get(url, params=params, timeout=35)
        return response.json()
    except Exception as e:
        print(f"❌ Ошибка getUpdates: {e}", flush=True)
        return {}

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_PROGNOZ, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()["result"]["message_id"]
        else:
            print(f"❌ Ошибка отправки: {response.status_code} - {response.text}", flush=True)
            return None
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}", flush=True)
        return None

def edit_message(message_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {"chat_id": CHANNEL_PROGNOZ, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            print(f"❌ Ошибка редактирования: {response.status_code} - {response.text}", flush=True)
            return False
    except Exception as e:
        print(f"❌ Ошибка редактирования: {e}", flush=True)
        return False

def parse_game(text):
    """Парсит игру баккара"""
    try:
        game_match = re.search(r'#N(\d+)', text)
        if not game_match:
            return None
        game_number = int(game_match.group(1))
        
        clean_text = text.replace('✅', '').replace('❌', '').replace('🔰', '')
        
        parts = clean_text.split('-')
        if len(parts) < 2:
            return None
        
        player_part = parts[0].strip()
        dealer_part = parts[1].strip()
        
        player_match = re.search(r'(\d+)\(([^)]+)\)', player_part)
        if not player_match:
            return None
        player_cards_str = player_match.group(2).strip()
        
        dealer_match = re.search(r'(\d+)\(([^)]+)\)', dealer_part)
        dealer_cards_str = dealer_match.group(2).strip() if dealer_match else ""
        
        player_cards = []
        for card in re.findall(r'([AKQJ]|10|\d)([♠♣♦♥]|♠️|♣️|♦️|♥️)', player_cards_str):
            rank, suit = card
            suit = suit.replace('♠', '♠️').replace('♣', '♣️').replace('♦', '♦️').replace('♥', '♥️')
            player_cards.append({"rank": rank, "suit": suit})
        
        dealer_cards = []
        for card in re.findall(r'([AKQJ]|10|\d)([♠♣♦♥]|♠️|♣️|♦️|♥️)', dealer_cards_str):
            rank, suit = card
            suit = suit.replace('♠', '♠️').replace('♣', '♣️').replace('♦', '♦️').replace('♥', '♥️')
            dealer_cards.append({"rank": rank, "suit": suit})
        
        return {
            "number": game_number,
            "player_cards": player_cards,
            "dealer_cards": dealer_cards,
            "text": text
        }
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}", flush=True)
        return None

def get_game_number():
    """Номер игры от 1 до 1440 (каждую минуту, старт в 03:00)"""
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
    return "".join(f"{c['rank']}{c['suit']}" for c in cards)

def calculate_score(cards):
    """Считает очки в баккара (последняя цифра суммы)"""
    if not cards:
        return 0
    
    score = 0
    rank_values = {"A": 1, "J": 0, "Q": 0, "K": 0}
    for card in cards:
        rank = card.get("rank", "")
        if rank.isdigit():
            score += int(rank)
        elif rank in rank_values:
            score += rank_values[rank]
    
    return score % 10

def is_game_finished(text):
    return "✅" in text or "❌" in text or "🔰" in text

def build_message(game_num, player_cards, dealer_cards, p_score, b_score):
    p_hand = format_cards(player_cards)
    b_hand = format_cards(dealer_cards)
    
    if p_score > b_score:
        result = "✅"
    elif b_score > p_score:
        result = "❌"
    else:
        result = "🔰"
    
    return f"#N{game_num}. {p_score}({p_hand}) - {result}{b_score}({b_hand}) #T{p_score + b_score}"

def get_offset():
    if os.path.exists(OFFSET_FILE):
        try:
            with open(OFFSET_FILE, "r") as f:
                return int(f.read().strip())
        except:
            return 0
    return 0

def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))

def load_recent_messages():
    """Загружает последние сообщения из канала"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"chat_id": CHANNEL_STATS, "limit": 100}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            messages = []
            for update in data.get("result", []):
                post = update.get("channel_post")
                if post and post.get("text"):
                    messages.append(post.get("text"))
            return messages
    except Exception as e:
        print(f"❌ Ошибка загрузки истории: {e}", flush=True)
    return []

# =====================================================================
# ОСНОВНОЙ ЦИКЛ
# =====================================================================
def main():
    print("🔄 ПАРСЕР БАККАРА (ЛАЙВ) ЗАПУЩЕН", flush=True)
    print(f"📊 Читает канал: {CHANNEL_STATS}", flush=True)
    print(f"📤 Отправляет в: {CHANNEL_PROGNOZ}", flush=True)
    print("=" * 60, flush=True)
    print("📌 Правила:", flush=True)
    print("   - Парсим игры баккара из канала", flush=True)
    print("   - Форматируем и постим в канал прогнозов", flush=True)
    print("=" * 60, flush=True)
    
    offset = get_offset()
    
    print("📥 Загрузка последних сообщений из канала...", flush=True)
    all_messages = load_recent_messages()
    print(f"📥 Загружено сообщений: {len(all_messages)}", flush=True)
    
    while True:
        try:
            updates = get_updates(offset)
            
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                save_offset(offset)
                
                channel_post = update.get("channel_post")
                edited_post = update.get("edited_channel_post")
                post = channel_post if channel_post else edited_post
                if not post:
                    continue
                
                chat_id = post.get("chat", {}).get("id")
                if str(chat_id) != str(CHANNEL_STATS):
                    continue
                
                text = post.get("text", "")
                if not text or "#N" not in text:
                    continue
                
                game_id_match = re.search(r'#N(\d+)', text)
                if not game_id_match:
                    continue
                game_number = int(game_id_match.group(1))
                
                all_messages.append(text)
                if len(all_messages) > 500:
                    all_messages = all_messages[-500:]
                
                if game_number in PROCESSED_GAMES:
                    continue
                
                if not is_game_finished(text):
                    print(f"⏳ Ожидание финальной раздачи для #N{game_number}", flush=True)
                    continue
                
                print(f"📥 {text[:50]}...", flush=True)
                
                game_data = parse_game(text)
                if not game_data:
                    print(f"❌ Не удалось распарсить #N{game_number}", flush=True)
                    continue
                
                # Формируем сообщение для отправки
                game_num = game_data["number"]
                player_cards = game_data["player_cards"]
                dealer_cards = game_data["dealer_cards"]
                p_score = calculate_score(player_cards) if player_cards else 0
                b_score = calculate_score(dealer_cards) if dealer_cards else 0
                
                msg = build_message(game_num, player_cards, dealer_cards, p_score, b_score)
                
                # Отправляем или редактируем
                if game_number in messages:
                    edit_message(messages[game_number], msg)
                    print(f"🔄 Обновлена игра {game_number}: {msg}", flush=True)
                else:
                    msg_id = send_message(msg)
                    if msg_id:
                        messages[game_number] = msg_id
                        print(f"📤 Новая игра {game_number}: {msg}", flush=True)
                
                if is_game_finished(text):
                    PROCESSED_GAMES.add(game_number)
                    print(f"🏁 Игра {game_number} завершена", flush=True)
                
                time.sleep(0.3)
            
            if len(PROCESSED_GAMES) > 500:
                PROCESSED_GAMES.clear()
            
            time.sleep(5)
            
        except Exception as e:
            print(f"❌ Ошибка: {e}", flush=True)
            time.sleep(10)

if __name__ == "__main__":
    main()