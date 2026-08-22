import requests
import json
import time
from datetime import datetime, timedelta
import pytz
import sys

# =====================================================================
# ПРИНУДИТЕЛЬНЫЙ ВЫВОД ЛОГОВ
# =====================================================================
sys.stdout.flush()
print("=" * 60, flush=True)
print("🃏 ПАРСЕР БАККАРА - ЧИСТАЯ ВЕРСИЯ", flush=True)
print("=" * 60, flush=True)

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
BOT_TOKEN = "5482422004:AAEKX1vcjzGbCYFrRL1MqKj4VymTGYwN7-c"
CHAT_ID = "-1003477065559"

MOSCOW_TZ = pytz.timezone('Europe/Moscow')
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

messages = {}
processed_games = set()

SUITS = {0: "♠️", 1: "♣️", 2: "♦️", 3: "♥️"}
RANKS = {1: "A", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://melbet-38497.pro/ru/live/baccarat/",
}

LIST_URL = "https://melbet-38497.pro/service-api/LiveFeed/Get1x2_VZip?sports=236&champs=2050671&count=40&gr=1521&mode=4&country=192&partner=8&getEmpty=true&virtualSports=true&noFilterBlockEvent=true"
DETAIL_URL = "https://melbet-38497.pro/service-api/LiveFeed/GetGameZip?id={game_id}&isSubGames=true&GroupEvents=true&countevents=250&grMode=4&partner=8&topGroups=&country=192&marketType=1&isNewBuilder=true"

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

def get_active_games():
    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        games = data.get("Value", []) if isinstance(data, dict) else []
        active = []
        for g in games:
            gid = g.get("I")
            if gid and str(gid) not in processed_games:
                active.append(g)
        return active
    except:
        return []

def get_game_data(game_id):
    try:
        url = DETAIL_URL.format(game_id=game_id)
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

def format_cards(cards):
    if not cards:
        return ""
    out = []
    for c in cards:
        cs = c.get("CS", 0)
        cv = c.get("CV", 0)
        if cv == 0 or cs == 0:
            return None
        suit = SUITS.get(cs, "?")
        rank = RANKS.get(cv, str(cv))
        out.append(f"{rank}{suit}")
    return "".join(out)

def calculate_score(cards):
    if not cards:
        return 0
    score = 0
    for c in cards:
        cv = c.get("CV", 0)
        if cv == 0:
            return -1
        if cv == 1:
            score += 1
        elif 2 <= cv <= 9:
            score += cv
    return score % 10

def is_early_win(p_score, d_score):
    return p_score in [8, 9] or d_score in [8, 9]

def is_finished_by_state(state):
    return state == "Игра завершена"

def get_game_type(p_score, d_score):
    if p_score == d_score:
        return "X"
    if is_early_win(p_score, d_score):
        return "R"
    return "N"

def build_message(game_num, player_cards, dealer_cards, p_score, d_score, state):
    p_hand = format_cards(player_cards)
    d_hand = format_cards(dealer_cards)
    if p_hand is None or d_hand is None:
        return None
    
    total = p_score + d_score
    gtype = get_game_type(p_score, d_score)
    
    if is_finished_by_state(state) or is_early_win(p_score, d_score):
        if p_score > d_score:
            result = "✅"
        elif d_score > p_score:
            result = "❌"
        else:
            result = "🔰"
        return f"#{gtype}{game_num}. {p_score}({p_hand}) - {result}{d_score}({d_hand}) #T{total}"
    
    arrow = "▶️" if dealer_cards else "◀️"
    return f"#{gtype}{game_num}. {p_score}({p_hand}) {arrow} {d_score}({d_hand}) #T{total}"

def send_message(text):
    try:
        r = requests.post(API + "/sendMessage", json={"chat_id": CHAT_ID, "text": text})
        if r.status_code == 200:
            return r.json()["result"]["message_id"]
    except:
        pass
    return None

def edit_message(msg_id, text):
    try:
        url = f"{API}/editMessageText"
        r = requests.post(url, json={"chat_id": CHAT_ID, "message_id": msg_id, "text": text})
        return r.status_code == 200
    except:
        return False

# =====================================================================
# ОСНОВНОЙ ЦИКЛ
# =====================================================================
def main():
    print("🔄 ПАРСЕР БАККАРА ЗАПУЩЕН", flush=True)
    print("=" * 60, flush=True)
    
    while True:
        try:
            games = get_active_games()
            if not games:
                time.sleep(2)
                continue
            
            for game in games:
                gid = str(game.get("I"))
                if gid in processed_games:
                    continue
                
                data = get_game_data(gid)
                if not data:
                    continue
                
                sc = data.get("Value", {}).get("SC", {})
                state = sc.get("CPS", "")
                
                player_cards = []
                dealer_cards = []
                
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
                
                if not player_cards:
                    continue
                
                # Фильтр пустых карт
                has_empty = False
                for c in player_cards + dealer_cards:
                    if c.get("CV", 0) == 0 or c.get("CS", 0) == 0:
                        has_empty = True
                        break
                if has_empty:
                    print(f"⏭️ Пропускаем {gid}: пустые карты", flush=True)
                    continue
                
                game_num = get_game_number()
                p_score = calculate_score(player_cards)
                d_score = calculate_score(dealer_cards) if dealer_cards else 0
                
                msg = build_message(game_num, player_cards, dealer_cards, p_score, d_score, state)
                if msg is None:
                    continue
                
                if gid in messages:
                    edit_message(messages[gid], msg)
                    print(f"🔄 Обновлена {gid}: {msg}", flush=True)
                else:
                    mid = send_message(msg)
                    if mid:
                        messages[gid] = mid
                        print(f"📤 Новая {gid}: {msg}", flush=True)
                
                if is_finished_by_state(state) or is_early_win(p_score, d_score):
                    processed_games.add(gid)
                    print(f"🏁 Завершена {gid}", flush=True)
                
                time.sleep(0.3)
            
            if len(processed_games) > 200:
                processed_games.clear()
            
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ Ошибка: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()