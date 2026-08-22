import requests
import json
import time
import os
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

# =====================================================================
# НАСТРОЙКИ - БЕРУТСЯ ТОЛЬКО С ХОСТИНГА!
# =====================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

if not BOT_TOKEN or not CHAT_ID:
    print("❌ ОШИБКА: BOT_TOKEN или CHAT_ID не найдены!", flush=True)
    exit(1)

try:
    CHAT_ID = int(CHAT_ID)
except:
    pass

print(f"✅ BOT_TOKEN загружен: {BOT_TOKEN[:5]}...", flush=True)
print(f"✅ CHAT_ID: {CHAT_ID}", flush=True)
print("=" * 60, flush=True)

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

LIST_URL = "https://melbet-38497.pro/service-api/LiveFeed/Get1x2_VZip?sports=236&champs=2050671&count=40&gr=1521&mode=4&country=192&partner=8&getEmpty=true&virtualSports=true&noFilterBlockEvent=true"
DETAIL_URL_TEMPLATE = "https://melbet-38497.pro/service-api/LiveFeed/GetGameZip?id={game_id}&isSubGames=true&GroupEvents=true&countevents=250&grMode=4&partner=8&topGroups=&country=192&marketType=1&isNewBuilder=true"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://melbet-38497.pro/",
}
NO_PROXY = {"http": None, "https": None}

SUITS_NAMES = {0: "♠️", 1: "♣️", 2: "♦️", 3: "♥️"}
RANKS = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}

messages = {}
processed_games = set()
game_cache = {}

# =====================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ТЕЛЕГРАМ
# =====================================================================
def send_telegram_message(text):
    try:
        url = f"{API_URL}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text}
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("result", {}).get("message_id")
        else:
            print(f"❌ Ошибка отправки: {resp.status_code} - {resp.text}", flush=True)
            return None
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}", flush=True)
        return None

def edit_telegram_message(message_id, text):
    try:
        url = f"{API_URL}/editMessageText"
        payload = {"chat_id": CHAT_ID, "message_id": message_id, "text": text}
        resp = requests.post(url, json=payload, timeout=5)
        return resp.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка редактирования: {e}", flush=True)
        return False

# =====================================================================
# ФУНКЦИИ ПАРСИНГА
# =====================================================================
def get_utc_game_number():
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now.hour * 60) + now.minute + 1

def format_cards(cards):
    if not cards:
        return ""
    result = []
    for c in cards:
        cs = c.get("S", 0)
        cv = c.get("R", 0)
        suit = SUITS_NAMES.get(cs, "?")
        rank = RANKS.get(cv, str(cv))
        result.append(f"{rank}{suit}")
    return "".join(result)

def calculate_score(cards):
    if not cards:
        return 0
    
    score = 0
    for c in cards:
        cv = c.get("R", 0)
        if cv >= 10:
            continue
        score += cv
    return score % 10

def is_game_finished(state, player_cards, dealer_cards):
    """Проверяет, завершена ли игра"""
    # 1. Если пришёл статус завершения
    if state in ["4", "5"]:
        return True
    
    # 2. Если у игрока 3 карты И у дилера 3 карты - игра точно завершена
    if len(player_cards) >= 3 and len(dealer_cards) >= 3:
        return True
    
    # 3. Если у игрока 3 карты И дилер не добирает (у него 2 карты и 5-6 очков)
    if len(player_cards) >= 3 and len(dealer_cards) == 2:
        d_score = calculate_score(dealer_cards)
        # В баккаре дилер добирает при 0-5, останавливается при 6-7
        if d_score >= 6:
            return True
    
    # 4. Если у дилера 3 карты И у игрока 2 карты (игрок не добирал)
    if len(dealer_cards) >= 3 and len(player_cards) == 2:
        p_score = calculate_score(player_cards)
        # Игрок добирает при 0-5, останавливается при 6-7
        if p_score >= 6:
            return True
    
    return False

def get_game_data(game_id):
    url = DETAIL_URL_TEMPLATE.format(game_id=game_id)
    try:
        response = requests.get(url, headers=HEADERS, timeout=5, proxies=NO_PROXY)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Статус игры {game_id}: {response.status_code}", flush=True)
    except Exception as e:
        print(f"❌ Ошибка игры {game_id}: {e}", flush=True)
    return None

def parse_game_data(data):
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
    
    return player_cards, dealer_cards, state

def build_message(game_num, player_cards, dealer_cards, p_score, d_score, state):
    p_hand = format_cards(player_cards)
    d_hand = format_cards(dealer_cards)
    total = p_score + d_score if dealer_cards else p_score
    
    # ПРОВЕРЯЕМ, ЗАВЕРШЕНА ЛИ ИГРА
    finished = is_game_finished(state, player_cards, dealer_cards)
    
    if finished:
        # Игра завершена - показываем победителя
        if p_score > d_score:
            return f"#N{game_num}. ✅{p_score}({p_hand}) - {d_score}({d_hand}) #T{total}"
        elif d_score > p_score:
            return f"#N{game_num}. {p_score}({p_hand}) - ✅{d_score}({d_hand}) #T{total}"
        elif p_score == d_score:
            return f"#N{game_num}. {p_score}({p_hand}) - 🔰{d_score}({d_hand}) #T{total}"
        else:
            return f"#N{game_num}. {p_score}({p_hand}) - {d_score}({d_hand}) #T{total}"
    
    # ИГРА ЕЩЁ ИДЁТ - показываем стрелку
    # Определяем, кто сейчас ходит
    if len(player_cards) == 2 and len(dealer_cards) == 0:
        arrow = "◀️"  # Игрок ходит (раздача)
    elif len(player_cards) == 2 and len(dealer_cards) == 1:
        arrow = "◀️"  # Игрок ходит
    elif len(player_cards) == 2 and len(dealer_cards) == 2:
        # У обоих по 2 карты - проверяем кто добирает
        if p_score <= 5:
            arrow = "◀️"  # Игрок добирает
        elif d_score <= 5 and p_score >= 6:
            arrow = "▶️"  # Дилер добирает
        else:
            arrow = "⏹️"  # Оба остановились (но игра не завершена)
    elif len(player_cards) == 3 and len(dealer_cards) == 2:
        if d_score <= 5:
            arrow = "▶️"  # Дилер добирает
        else:
            arrow = "⏹️"  # Дилер остановился
    elif len(player_cards) == 2 and len(dealer_cards) == 3:
        arrow = "⏹️"  # Игрок остановился
    else:
        arrow = "⏹️"
    
    return f"#N{game_num}. {p_score}({p_hand}) {arrow} {d_score}({d_hand}) #T{total}"

def get_active_games():
    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=5, proxies=NO_PROXY)
        if resp.status_code == 200:
            games = resp.json().get("Value", [])
            
            active_games = []
            for game in games:
                game_id = game.get("I")
                if game_id and str(game_id) not in processed_games:
                    scores = game.get("SC", {})
                    fs = scores.get("FS", {})
                    s1 = fs.get("S1", 0)
                    s2 = fs.get("S2", 0)
                    is_finished = scores.get("CPS") == "Игра завершена"
                    
                    if (s1 > 0 or s2 > 0 or not is_finished):
                        active_games.append(game)
                        print(f"✅ Найдена игра: {game_id}", flush=True)
            
            return active_games
        else:
            print(f"⚠️ Статус API: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
    return []

# =====================================================================
# ОСНОВНОЙ ЦИКЛ
# =====================================================================
def main():
    global processed_games
    
    print("🔄 ПАРСЕР БАККАРА ЗАПУЩЕН", flush=True)
    print("🕐 Игры каждую минуту", flush=True)
    print("=" * 60, flush=True)
    
    while True:
        try:
            active_games = get_active_games()
            
            if not active_games:
                print("💤 Нет активных игр, ждём 3 секунды...", flush=True)
                time.sleep(3)
                continue
            
            for game in active_games:
                game_id = str(game.get("I"))
                
                if game_id in processed_games:
                    continue
                
                data = get_game_data(game_id)
                if not data:
                    continue
                
                player_cards, dealer_cards, state = parse_game_data(data)
                
                if not player_cards:
                    continue
                
                game_number = get_utc_game_number()
                p_score = calculate_score(player_cards)
                d_score = calculate_score(dealer_cards) if dealer_cards else 0
                
                msg = build_message(game_number, player_cards, dealer_cards, p_score, d_score, state)
                
                if game_id in messages:
                    edit_telegram_message(messages[game_id], msg)
                    print(f"🔄 Обновлена игра {game_id}: {msg}", flush=True)
                else:
                    msg_id = send_telegram_message(msg)
                    if msg_id:
                        messages[game_id] = msg_id
                        print(f"📤 Новая игра {game_id}: {msg}", flush=True)
                
                # Проверяем завершение игры
                if is_game_finished(state, player_cards, dealer_cards):
                    processed_games.add(game_id)
                    print(f"🏁 Игра {game_id} завершена", flush=True)
                
                time.sleep(0.5)
            
            if len(processed_games) > 200:
                processed_games.clear()
                messages.clear()
                print("🗑️ Кэш очищен", flush=True)
            
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(5)

if __name__ == "__main__":
    main()