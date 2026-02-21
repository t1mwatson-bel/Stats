import os
import asyncio
import requests
import json
from datetime import datetime
from telegram import Bot
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== НАСТРОЙКИ ==========
TOKEN = os.getenv("8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003179573402"))
API_BASE = "https://1xlite-7636770.bar"
GAME_IDS = [697705521, 697704425]

SUIT_MAP = {1: '♥️', 2: '♠️', 3: '♣️', 4: '♦️'}
RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}

game_counter = 1248

bot = Bot(token=TOKEN)
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
                except json.JSONDecodeError:
                    continue
        
        # Парсинг карт БЕЗ f-строк (исправленная версия)
        def parse_cards(cards_list):
            result = []
            for card in cards_list:
                if isinstance(card, dict):
                    rank_num = card.get('R', 0)
                    suit_code = card.get('S', 0)
                    
                    # Ранг
                    if rank_num in RANK_MAP:
                        rank_str = RANK_MAP[rank_num]
                    elif 2 <= rank_num <= 10:
                        rank_str = str(rank_num)
                    else:
                        rank_str = '?'
                    
                    # Масть
                    suit_str = SUIT_MAP.get(suit_code, '?')
                    
                    result.append(rank_str + suit_str)
            return result
        
        # Подсчет очков
        def calculate_score(cards_list):
            total = 0
            for card in cards_list:
                if isinstance(card, dict):
                    rank = card.get('R', 0)
                    if rank in [1, 14]:  # Туз
                        total += 1
                    elif rank in [11, 12, 13]:  # J, Q, K
                        total += 0
                    elif 2 <= rank <= 10:
                        total += rank
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
        print(f"Ошибка API: {e}")
        return None

async def send_game_message():
    global game_counter
    
    for game_id in GAME_IDS:
        game_data = get_game_data(game_id)
        
        if game_data and game_data['player_cards'] and game_data['banker_cards']:
            # Формируем сообщение ТОЧНО как нужно
            player_side = f"{game_data['player_score']} ({game_data['player_cards']})"
            banker_side = f"✅{game_data['banker_score']} ({game_data['banker_cards']})"
            
            message = f"""#N{game_counter} {player_side} - {banker_side}
#П2 #T2 #C3_3"""
            
            try:
                await bot.send_message(CHANNEL_ID, message)
                print(f"✅ Отправлено #N{game_counter}: {message}")
                game_counter += 1
                return True
            except Exception as e:
                print(f"❌ Ошибка Telegram: {e}")
                return False
    
    print("❌ Нет данных от 1xBet API")
    return False

async def main():
    print(f"🚀 Баккара статистика запущена! Стартуем с #N{game_counter}")
    print("⏳ Мониторим 1xBet API...")
    
    last_states = {}
    
    while True:
        try:
            success = await send_game_message()
            if success:
                await asyncio.sleep(10)  # Пауза 10 сек между играми
            else:
                await asyncio.sleep(5)   # Быстрее пробуем снова
        except KeyboardInterrupt:
            print("🛑 Остановлено пользователем")
            break
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
