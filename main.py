import os
import asyncio
import requests
import json
from datetime import datetime
from telegram import Bot
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== ДЕБАГ Variables ==========
print("🔍 DEBUG: Все переменные окружения:")
for key, value in os.environ.items():
    if 'TOKEN' in key or 'CHANNEL' in key:
        print(f"   {key} = {value[:10]}...")

TOKEN = os.getenv("TOKEN", "8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003179573402"))

print(f"🔍 TOKEN получен: {'✅' if TOKEN else '❌ ПУСТО!' }")
print(f"🔍 TOKEN preview: {TOKEN[:20] if TOKEN else 'None'}...")
print(f"🔍 CHANNEL_ID: {CHANNEL_ID}")

if not TOKEN:
    print("❌ ОСТАНОВКА: TOKEN не найден в Variables!")
    print("   Railway → Settings → Variables → TOKEN = 8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6")
    exit(1)

# ========== НАСТРОЙКИ ==========
API_BASE = "https://1xlite-7636770.bar"
GAME_IDS = [697705521, 697704425]
SUIT_MAP = {1: '♥️', 2: '♠️', 3: '♣️', 4: '♦️'}
RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
game_counter = 1248

print("✅ Создаём Bot...")
bot = Bot(token=TOKEN)
print("✅ Bot создан!")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://1xlite-7636770.bar/',
}

def get_game_data(game_id):
    try:
        response = requests.get(
            f"{API_BASE}/service-api/LiveFeed/GetGameZip",
            headers=HEADERS,
            params={'id': game_id},
            timeout=10,
            verify=False
        )
        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code}")
            return None
        
        details = response.json()
        if not details or not details.get('Value'):
            return None
        
        sc = details['Value'].get('SC', {})
        player_cards = []
        banker_cards = []
        
        for item in sc.get('S', []):
            if isinstance(item, dict) and item.get('Key') in ['P', 'B']:
                try:
                    cards = json.loads(item.get('Value', '[]'))
                    if item['Key'] == 'P':
                        player_cards = cards
                    else:
                        banker_cards = cards
                except:
                    continue
        
        def parse_cards(cards_list):
            result = []
            for card in cards_list:
                if isinstance(card, dict):
                    rank_num = card.get('R', 0)
                    suit_code = card.get('S', 0)
                    rank = RANK_MAP.get(rank_num, str(rank_num) if 2 <= rank_num <= 10 else '?')
                    suit = SUIT_MAP.get(suit_code, '?')
                    result.append(rank + suit)
            return result
        
        def calculate_score(cards_list):
            total = 0
            for card in cards_list:
                if isinstance(card, dict):
                    rank = card.get('R', 0)
                    if rank in [1, 14]: total += 1
                    elif rank in [11, 12, 13]: total += 0
                    elif 2 <= rank <= 10: total += rank
            return total % 10
        
        player_parsed = parse_cards(player_cards)
        banker_parsed = parse_cards(banker_cards)
        
        return {
            'player_score': calculate_score(player_cards),
            'player_cards': ' '.join(player_parsed),
            'banker_score': calculate_score(banker_cards),
            'banker_cards': ' '.join(banker_parsed)
        }
    except Exception as e:
        print(f"❌ API Error: {e}")
        return None

async def send_game_message():
    global game_counter
    
    print(f"⏳ Проверяем 1xBet API...")
    for game_id in GAME_IDS:
        game_data = get_game_data(game_id)
        
        if game_data and game_data['player_cards'] and game_data['banker_cards']:
            player_side = f"{game_data['player_score']} ({game_data['player_cards']})"
            banker_side = f"✅{game_data['banker_score']} ({game_data['banker_cards']})"
            
            message = f"""#N{game_counter} {player_side} - {banker_side}
#П2 #T2 #C3_3"""
            
            try:
                await bot.send_message(CHANNEL_ID, message)
                print(f"✅ #N{game_counter} ОТПРАВЛЕНО В КАНАЛ!")
                game_counter += 1
                return True
            except Exception as e:
                print(f"❌ Telegram Error: {e}")
                return False
    
    print("❌ Нет данных от 1xBet")
    return False

async def main():
    print(f"🚀 Баккара статистика #N{game_counter} запущена!")
    
    while True:
        try:
            await send_game_message()
            await asyncio.sleep(10)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
