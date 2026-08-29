import os
import sys
import requests
import json
import time
from datetime import datetime, timedelta
import pytz

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    BOT_TOKEN = os.getenv('BOT_TOKEN_PROGNOZ')

CHAT_ID = os.getenv('CHAT_ID_21')
if not CHAT_ID:
    CHAT_ID = os.getenv('CHAT_ID')

if not BOT_TOKEN or not CHAT_ID:
    print("❌ Ошибка: BOT_TOKEN или CHAT_ID не заданы!", flush=True)
    sys.exit(1)

print(f"✅ BOT_TOKEN: {BOT_TOKEN[:5]}...", flush=True)
print(f"✅ CHAT_ID: {CHAT_ID}", flush=True)

MOSCOW_TZ = pytz.timezone('Europe/Moscow')
BASE_URL = "https://1xlite-36553.pro"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
messages = {}
processed_games = set()
game_numbers = {}  
player_cards_history = {}  
dealer_cards_history = {}  
game_state_history = {}  

SUITS_NAMES = {0: "♠️", 1: "♣️", 2: "♦️", 3: "♥️"}
RANKS = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE_URL}/ru/live/twentyone/1643503-twentyone-game",
    "Cookie": "platform_type=desktop; lng=ru; cookies_agree_type=3; tzo=3; is12h=0; referral_values=%7B%22type%22%3A%22reflinkid%22%2C%22val%22%3A%22s_50970m_355c_%22%2C%22additional%22%3A%7B%22name_tag%22%3A%22tag%22%7D%7D; reflinkid=s_50970m_355c_; auid=uaJb+WqQFLEHP+WbAwdUAg==; fatman_uuid=6dac517c-7199-1491-828a-723ace371af0; che_g=3741ad9b-2648-4e11-b16e-55cbdda04b42; SESSION=ae9f1b4deac37d41be6873b1acf03cf4; sh.session.id=1e645679-820b-4250-86f5-bf39161d311d; _ga=GA1.1.103981619.1787827389; _ym_uid=1787827389562709649; _ym_d=1787827389; _ym_isad=2; _ym_visorc=b; mdd=1; _ga_7JGWL9SV66=GS2.1.s1787827388$o1$g1$t1787827414$j34$l0$h1219464045; window_width=150"
}

print("✅ Настройки для обычной 21 загружены", flush=True)

def get_game_number():
    now = datetime.now(MOSCOW_TZ)
    start = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now < start:
        start = start - timedelta(days=1)
    diff_minutes = (now - start).total_seconds() / 60
    return int(diff_minutes) % 1440 + 1

def get_active_games():
    try:
        url = f"{BASE_URL}/service-api/main-live-feed/v3/games1x2?cfView=3&count=40&fcountry=190&gr=415&grMode=4&lng=ru&ref=7&selectedMs=10.146.1643503"
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return []
        data = response.json()
        if isinstance(data, list):
            games = data
        elif isinstance(data, dict) and "Value" in data:
            games = data.get("Value", [])
        else:
            return []
        return [g for g in games if g.get("liga", {}).get("id") == 1643503 and g.get("id")]
    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
        return []

def get_game_data(game_id):
    url = f"{BASE_URL}/service-api/LiveFeed/GetGameZip?id={game_id}&isSubGames=true&GroupEvents=true&countevents=250&grMode=4&partner=7&topGroups=&country=190&marketType=1&isNewBuilder=true"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"❌ Ошибка игры {game_id}: {e}", flush=True)
    return None

def format_cards(cards):
    if not cards:
        return ""
    return "".join(f"{RANKS.get(c.get('CV',0), str(c.get('CV',0)))}{SUITS_NAMES.get(c.get('CS',0), '?')}" for c in cards)

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
    if aces == 2:
        return 21
    while score > 21 and aces > 0:
        score -= 10
        aces -= 1
    return score

def get_arrow(state):
    if state == "1":
        return "◀️"
    elif state in ("2", "3"):
        return "▶️"
    return ""

def build_message(game_num, player_cards, dealer_cards, p_score, d_score, state):
    p_hand = format_cards(player_cards)
    d_hand = format_cards(dealer_cards)
    total = p_score + (d_score if dealer_cards else 0)
    
    if state in ("4", "5") or (dealer_cards and d_score > 21) or (dealer_cards and d_score >= 20) or len(player_cards) >= 5 or len(dealer_cards) >= 5:
        tags = []
        if len(player_cards) == 2 and len(dealer_cards) == 2:
            tags.append("#R")
        player_aces = sum(1 for c in player_cards if c.get("CV") == 14)
        dealer_aces = sum(1 for c in dealer_cards if c.get("CV") == 14)
        if player_aces == 2 or dealer_aces == 2:
            tags.append("#G")
        if p_score == 21 or d_score == 21:
            tags.append("#O")
        if p_score == d_score:
            tags.append("#X")
        tag_str = " " + " ".join(tags) if tags else ""
        if p_score > 21:
            return f"#N{game_num}. {p_score}({p_hand}) - ✅{d_score}({d_hand}) #T{total}{tag_str}"
        if d_score > 21:
            return f"#N{game_num}. ✅{p_score}({p_hand}) - {d_score}({d_hand}) #T{total}{tag_str}"
        if p_score == 21:
            return f"#N{game_num}. ✅{p_score}({p_hand}) - {d_score}({d_hand}) #T{total}{tag_str}"
        if d_score == 21:
            return f"#N{game_num}. {p_score}({p_hand}) - ✅{d_score}({d_hand}) #T{total}{tag_str}"
        if p_score > d_score:
            return f"#N{game_num}. ✅{p_score}({p_hand}) - {d_score}({d_hand}) #T{total}{tag_str}"
        if d_score > p_score:
            return f"#N{game_num}. {p_score}({p_hand}) - ✅{d_score}({d_hand}) #T{total}{tag_str}"
        return f"#N{game_num}. {p_score}({p_hand}) - 🔰{d_score}({d_hand}) #T{total}{tag_str}"
    
    arrow = get_arrow(state)
    return f"#N{game_num}. {p_score}({p_hand}) {arrow} {d_score}({d_hand}) #T{total}"

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
        r = requests.post(f"{API}/editMessageText", json={"chat_id": CHAT_ID, "message_id": message_id, "text": text})
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка редактирования: {e}", flush=True)
        return False

# =============================================================
# ТОЛЬКО ЭТА ФУНКЦИЯ ИЗМЕНЕНА
# =============================================================
def is_game_finished(state, player_cards, dealer_cards, p_score, d_score):
    if state == "5":
        return True
    if state == "4":
        if dealer_cards and d_score in (20, 21):
            return True
        return False
    if state in ("2", "3"):
        return False
    if dealer_cards and d_score > 21:
        return True
    if len(player_cards) >= 5 or len(dealer_cards) >= 5:
        return True
    return False

def monitor_active_games():
    global processed_games, messages, player_cards_history, dealer_cards_history, game_numbers, game_state_history
    
    active_games = get_active_games()
    if not active_games:
        return
    
    for game in active_games:
        game_id = str(game.get("id"))
        if game_id in processed_games:
            continue
        
        data = get_game_data(game_id)
        if not data:
            continue
        
        sc = data.get("Value", {}).get("SC", {})
        player_cards = []
        dealer_cards = []
        state = None
        
        for item in sc.get("S", []):
            if item.get("Key") == "P1":
                try:
                    player_cards = json.loads(item.get("Value", "[]"))
                except:
                    player_cards = []
            elif item.get("Key") == "P2":
                try:
                    dealer_cards = json.loads(item.get("Value", "[]"))
                except:
                    dealer_cards = []
            elif item.get("Key") == "STATE":
                state = item.get("Value")
        
        if not player_cards:
            continue
        
        if game_id not in game_numbers:
            game_numbers[game_id] = get_game_number()
        game_number = game_numbers[game_id]
        
        p1_str = json.dumps(player_cards)
        p2_str = json.dumps(dealer_cards)
        
        cards_changed = (game_id not in player_cards_history or player_cards_history[game_id] != p1_str or
                         game_id not in dealer_cards_history or dealer_cards_history[game_id] != p2_str)
        state_changed = (game_id not in game_state_history or game_state_history[game_id] != state)
        
        if not cards_changed and not state_changed:
            continue
        
        player_cards_history[game_id] = p1_str
        dealer_cards_history[game_id] = p2_str
        game_state_history[game_id] = state
        
        p_score = calculate_score(player_cards)
        d_score = calculate_score(dealer_cards) if dealer_cards else 0
        
        msg = build_message(game_number, player_cards, dealer_cards, p_score, d_score, state)
        
        if game_id in messages:
            edit_message(messages[game_id], msg)
            print(f"🔄 Обновлена игра {game_id}: {msg}", flush=True)
        else:
            msg_id = send_message(msg)
            if msg_id:
                messages[game_id] = msg_id
                print(f"📤 Новая игра {game_id}: {msg}", flush=True)
        
        if is_game_finished(state, player_cards, dealer_cards, p_score, d_score):
            processed_games.add(game_id)
            for d in (messages, game_numbers, player_cards_history, dealer_cards_history, game_state_history):
                if game_id in d:
                    del d[game_id]
            print(f"🏁 Игра {game_id} завершена (state={state}, d_score={d_score})", flush=True)

def main():
    global processed_games, messages, game_numbers, player_cards_history, dealer_cards_history, game_state_history
    print("🔄 ПАРСЕР ОБЫЧНОЙ 21 ЗАПУЩЕН (ЛАЙВ-МОНИТОРИНГ)", flush=True)
    print("⏱️ Мониторинг: каждые 10 секунд", flush=True)
    print("=" * 60, flush=True)
    
    last_monitor_time = time.time()
    while True:
        try:
            if time.time() - last_monitor_time >= 10:
                monitor_active_games()
                last_monitor_time = time.time()
            if len(processed_games) > 500:
                processed_games.clear()
                game_numbers.clear()
                player_cards_history.clear()
                dealer_cards_history.clear()
                game_state_history.clear()
                messages.clear()
                print("🗑️ Кэш очищен", flush=True)
            time.sleep(1)
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(5)

if __name__ == "__main__":
    main()