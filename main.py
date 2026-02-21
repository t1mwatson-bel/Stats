import requests, json, time, asyncio
from datetime import datetime
import urllib3

urllib3.disable_warnings()

# ========== НАСТРОЙКИ ==========
API_BASE = "https://1xlite-7636770.bar"
GAME_IDS = [697705521, 697704425]
TOKEN = "8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU"
CHANNEL_ID = -1003179573402

HEADERS = {'User-Agent':'Mozilla/5.0','Accept':'application/json,*/*','Referer':'https://1xlite-7636770.bar/'}
SUIT_MAP = {1:'♥️', 2:'♠️', 3:'♣️', 4:'♦️'}
RANK_MAP = {1:'A', 11:'J', 12:'Q', 13:'K', 14:'A'}

game_counter = 1248  # Начинаем с твоего номера
from telegram import Bot
bot = Bot(token=TOKEN)

def get_game_data(game_id):
    try:
        r = requests.get(f"{API_BASE}/service-api/LiveFeed/GetGameZip", 
                        headers=HEADERS, params={'id':game_id}, timeout=10, verify=False)
        if r.status_code != 200: return None
        
        details = r.json()
        if not details or not details.get('Value'): return None
        
        sc = details['Value'].get('SC', {})
        player_cards, banker_cards = [], []
        
        for item in sc.get('S', []):
            if isinstance(item, dict) and item.get('Key') in ['P', 'B']:
                cards = json.loads(item.get('Value', '[]'))
                if item['Key'] == 'P': player_cards = cards
                else: banker_cards = cards
        
        def parse_cards(cards):
            return [f"{RANK_MAP.get(c.get('R'), str(c.get('R', ''))}{SUIT_MAP.get(c.get('S', 0), '?')}" 
                   for c in cards]
        
        def calc_score(cards):
            return sum(1 if c.get('R') in [1,14] else 0 if c.get('R') in [11,12,13] 
                      else min(c.get('R', 0), 10) for c in cards) % 10
        
        player_str = ' '.join(parse_cards(player_cards))
        banker_str = ' '.join(parse_cards(banker_cards))
        
        return {
            'player_score': calc_score(player_cards),
            'player_cards': player_str,
            'banker_score': calc_score(banker_cards),
            'banker_cards': banker_str
        }
    except: return None

async def send_game_message(game_data):
    global game_counter
    
    # ТОЧНО как на твоём примере
    player_side = f"{game_data['player_score']} ({game_data['player_cards']})"
    banker_side = f"✅{game_data['banker_score']} ({game_data['banker_cards']})"
    
    message = f"""#N{game_counter} {player_side} - {banker_side}
#П2 #T2 #C3_3"""
    
    await bot.send_message(CHANNEL_ID, message)
    print(f"✅ Отправлено #N{game_counter}: {message}")
    
    game_counter += 1

async def main():
    global game_counter
    print(f"🚀 КАНАЛ СТАТИСТИКИ БАККАРА 1xBet (стартуем с #N{game_counter})")
    
    last_states = {}
    
    while True:
        for game_id in GAME_IDS:
            game_data = get_game_data(game_id)
            
            if game_data and game_data['player_cards'] and game_data['banker_cards']:
                state = f"{game_data['player_cards']}_{game_data['banker_cards']}"
                
                if game_id not in last_states or last_states[game_id] != state:
                    await send_game_message(game_data)
                    last_states[game_id] = state
                    await asyncio.sleep(2)  # Пауза между играми
        
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
