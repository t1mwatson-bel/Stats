import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
import urllib3
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# Отключаем предупреждения о SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== НАСТРОЙКА ЛОГИРОВАНИЯ =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ===== ПЕРЕМЕННЫЕ =====
TOKEN = os.getenv("TOKEN")
API_BASE = os.getenv("API_BASE", "https://1xlite-7636770.bar")
CHAT_ID = os.getenv("CHAT_ID")  # Добавьте переменную для chat_id
GAME_IDS = [697705521, 697704425]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://1xlite-7636770.bar/',
}

# Маппинг рангов и мастей
RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
SUIT_MAP = {1: '♥️', 2: '♠️', 3: '♣️', 4: '♦️'}

# ===== ПРЯМАЯ ПРОВЕРКА API =====
def test_api_connection():
    logger.info("=" * 50)
    logger.info("ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЯ К API")
    logger.info("=" * 50)
    
    # Проверка основного домена
    try:
        response = requests.get(API_BASE, timeout=5, verify=False)
        logger.info(f"Основной домен: {response.status_code}")
    except Exception as e:
        logger.error(f"Основной домен недоступен: {e}")
    
    # Проверка данных для игр
    for game_id in GAME_IDS:
        url = f"{API_BASE}/service-api/LiveFeed/GetGameZip"
        params = {'id': game_id, 'country': 1, 'marketType': 1}
        
        try:
            logger.info(f"Пробуем получить игру {game_id}...")
            response = requests.get(url, headers=HEADERS, params=params, timeout=10, verify=False)
            logger.info(f"Статус: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('Success'):
                    logger.info(f"✅ Успешно! Есть данные для игры {game_id}")
                    check_cards(data)
                else:
                    logger.warning(f"API вернул Success=false для игры {game_id}")
            else:
                logger.error(f"Ошибка HTTP {response.status_code} для игры {game_id}")
                
        except Exception as e:
            logger.error(f"Ошибка при тестировании игры {game_id}: {e}")
    
    logger.error("❌ НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ НИ ОДНОЙ ИГРЫ")

def check_cards(data):
    value = data.get('Value', {})
    sc = value.get('SC', {})
    
    if 'S' in sc:
        for item in sc['S']:
            if item.get('Key') in ['P', 'B']:
                cards = json.loads(item.get('Value', '[]'))
                logger.info(f"  {item['Key']} карты: {cards}")

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С API =====
def get_game_details(game_id):
    url = f"{API_BASE}/service-api/LiveFeed/GetGameZip"
    params = {
        'id': game_id,
        'isSubGames': 'true',
        'GroupEvents': 'true',
        'countevents': 250,
        'grMode': 4,
        'country': 1,
        'marketType': 1,
        'isNewBuilder': 'true'
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15, verify=False)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"HTTP {response.status_code} для игры {game_id}")
            return None
    except Exception as e:
        logger.error(f"Ошибка запроса для игры {game_id}: {e}")
        return None

def extract_cards(details):
    if not details:
        return [], []
    
    try:
        value = details.get('Value', {})
        sc = value.get('SC', {})
        
        player_cards = []
        banker_cards = []
        
        if 'S' in sc:
            for item in sc['S']:
                if isinstance(item, dict):
                    key = item.get('Key')
                    if key in ['P', 'B']:
                        try:
                            cards = json.loads(item.get('Value', '[]'))
                            if key == 'P':
                                player_cards = cards
                            else:
                                banker_cards = cards
                            logger.info(f"Найдены карты {key}: {cards}")
                        except Exception as e:
                            logger.error(f"Ошибка парсинга карт {key}: {e}")
        
        for item in sc.get('S', []):
            if item.get('Key') == 'S':
                logger.info(f"Статус игры: {item.get('Value')}")
        
        return player_cards, banker_cards
    except Exception as e:
        logger.error(f"Ошибка извлечения карт: {e}")
        return [], []

def parse_card(card):
    if not isinstance(card, dict):
        return '??'
    
    rank = card.get('R')
    suit = card.get('S', 0)
    
    if rank in RANK_MAP:
        rank_str = RANK_MAP[rank]
    elif rank and 2 <= rank <= 10:
        rank_str = str(rank)
    else:
        rank_str = '?'
    
    suit_str = SUIT_MAP.get(suit, '?')
    
    return f"{rank_str}{suit_str}"

def calculate_score(cards):
    total = 0
    for card in cards:
        if isinstance(card, dict):
            rank = card.get('R', 0)
            if rank in [1, 14]:
                total += 1
            elif rank in [11, 12, 13]:
                total += 0
            elif 2 <= rank <= 10:
                total += rank
    return total % 10

def get_game_info(game_id):
    logger.info(f"Получение данных для игры {game_id}...")
    details = get_game_details(game_id)
    
    if not details:
        logger.warning(f"Нет данных для игры {game_id}")
        return None
    
    player_cards, banker_cards = extract_cards(details)
    
    if not player_cards and not banker_cards:
        logger.warning(f"Нет карт для игры {game_id}")
        return None
    
    player_score = calculate_score(player_cards)
    banker_score = calculate_score(banker_cards)
    
    winner = 'Tie' if player_score == banker_score else 'Player' if player_score > banker_score else 'Banker'
    
    result = {
        'game_id': game_id,
        'player_cards': [parse_card(c) for c in player_cards],
        'banker_cards': [parse_card(c) for c in banker_cards],
        'player_score': player_score,
        'banker_score': banker_score,
        'winner': winner,
        'raw_player': player_cards,
        'raw_banker': banker_cards
    }
    
    logger.info(f"Результат игры {game_id}: Player={result['player_cards']} ({player_score}), Banker={result['banker_cards']} ({banker_score})")
    return result

def format_game_message(game):
    return (
        f"🎲 <b>Игра {game['game_id']}</b>\n"
        f"Player: {' '.join(game['player_cards'])} = {game['player_score']}\n"
        f"Banker: {' '.join(game['banker_cards'])} = {game['banker_score']}\n"
        f"Победитель: {game['winner']}"
    )

# ===== TELEGRAM ФУНКЦИИ =====
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            logger.info(f"Сообщение отправлено в чат {chat_id}")
            return True
        else:
            logger.error(f"Ошибка отправки: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при отправке: {e}")
        return False

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {'timeout': 30}
    if offset:
        params['offset'] = offset
    
    try:
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 200:
            return response.json().get('result', [])
    except Exception as e:
        logger.error(f"Ошибка getUpdates: {e}")
    return []

# ===== ОСНОВНОЙ ЦИКЛ =====
def main():
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК БОТА С ПРЯМОЙ ПРОВЕРКОЙ ИГР")
    logger.info("=" * 60)
    
    # Проверяем токен
    try:
        me = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe").json()
        if me.get('ok'):
            logger.info(f"✅ Бот авторизован: @{me['result']['username']}")
        else:
            logger.error("❌ Неверный токен!")
            return
    except Exception as e:
        logger.error(f"❌ Ошибка проверки токена: {e}")
        return
    
    # Тестируем API игры
    logger.info("\n🔍 ПРОВЕРКА API ИГР...")
    api_working = test_api_connection()
    
    if not api_working:
        logger.error("❌ API игр не работает! Бот не сможет получать данные.")
    
    # Пробуем сразу получить данные
    logger.info("\n🔍 ПРОБУЕМ ПОЛУЧИТЬ ИГРЫ СЕЙЧАС:")
    for game_id in GAME_IDS:
        game = get_game_info(game_id)
        if game:
            logger.info(f"✅ Игра {game_id}: {format_game_message(game)}")
            send_telegram_message(CHAT_ID, format_game_message(game))  # Отправляем сообщение в канал
        else:
            logger.info(f"❌ Игра {game_id}: данных нет")
    
    last_update_id = 0
    last_games = {}
    send_count = 0
    
    logger.info("\n✅ Бот запущен и готов к работе!")
    logger.info("=" * 60)
    
    while True:
        try:
            updates = get_updates(last_update_id + 1)
            
            for update in updates:
                last_update_id = update['update_id']
                
                if 'message' in update and 'text' in update['message']:
                    chat_id = update['message']['chat']['id']
                    text = update['message']['text']
                    
                    logger.info(f"Команда от {chat_id}: {text}")
                    
                    if text == '/start':
                        send_telegram_message(chat_id, 
                            "🤖 Бот для баккары запущен!\n\n"
                            "Команды:\n"
                            "/check - проверить игры сейчас\n"
                            "/test - тест API\n"
                            "/status - статус бота"
                        )
                    
                    elif text == '/test':
                        send_telegram_message(chat_id, "🔍 Тестирую подключение к API...")
                        if test_api_connection():
                            send_telegram_message(chat_id, "✅ API работает!")
                        else:
                            send_telegram_message(chat_id, "❌ API не отвечает!")
                    
                    elif text == '/status':
                        msg = f"📊 Статус бота:\n"
                        msg += f"Отслеживается игр: {len(GAME_IDS)}\n"
                        msg += f"Последних отправок: {send_count}"
                        send_telegram_message(chat_id, msg)
                    
                    elif text == '/check':
                        send_telegram_message(chat_id, "🔍 Проверяю игры...")
                        
                        for game_id in GAME_IDS:
                            game = get_game_info(game_id)
                            if game:
                                send_telegram_message(chat_id, format_game_message(game))
                                send_count += 1
                            else:
                                send_telegram_message(chat_id, f"❌ Нет данных для игры {game_id}")
            
            current_time = int(time.time())
            if current_time % 10 < 2:
                logger.info("🔄 Автоматическая проверка игр...")
                
                for game_id in GAME_IDS:
                    game = get_game_info(game_id)
                    if game:
                        state_key = f"{game['player_cards']}_{game['banker_cards']}"
                        
                        if last_games.get(game_id) != state_key:
                            logger.info(f"⚡ ИЗМЕНЕНИЕ в игре {game_id}: {state_key}")
                            send_telegram_message(CHAT_ID, format_game_message(game))  # Отправляем изменение в канал
                            last_games[game_id] = state_key
            
            time.sleep(2)
            
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен")
            break
        except Exception as e:
            logger.error(f"Ошибка в основном цикле: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()