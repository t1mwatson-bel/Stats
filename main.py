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
TOKEN = os.getenv("TOKEN")  # ИСПРАВЛЕНО: берем по имени переменной
API_BASE = os.getenv("API_BASE", "https://1xlite-7636770.bar")
CHAT_ID = os.getenv("CHAT_ID")  # ИСПРАВЛЕНО: берем по имени переменной
GAME_IDS = [697705521, 697704425]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': f'{API_BASE}/',
}

# Маппинг рангов и мастей
RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
SUIT_MAP = {1: '♥️', 2: '♠️', 3: '♣️', 4: '♦️'}

# ===== ПРЯМАЯ ПРОВЕРКА API =====
def test_api_connection():
    logger.info("=" * 50)
    logger.info("ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЯ К API")
    logger.info("=" * 50)
    
    success_count = 0
    
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
                if data and data.get('Success'):
                    logger.info(f"✅ Успешно! Есть данные для игры {game_id}")
                    check_cards(data)
                    success_count += 1
                else:
                    logger.warning(f"API вернул Success=false для игры {game_id}")
            else:
                logger.error(f"Ошибка HTTP {response.status_code} для игры {game_id}")
                
        except Exception as e:
            logger.error(f"Ошибка при тестировании игры {game_id}: {e}")
    
    if success_count == 0:
        logger.error("❌ НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ НИ ОДНОЙ ИГРЫ")
        return False
    else:
        logger.info(f"✅ Успешно получены данные для {success_count} игр")
        return True

def check_cards(data):
    """Проверяет наличие карт в данных"""
    if not data or not isinstance(data, dict):
        return
    
    value = data.get('Value', {})
    if not value:
        return
        
    sc = value.get('SC', {})
    if not sc:
        return
    
    if 'S' in sc:
        for item in sc['S']:
            if isinstance(item, dict) and item.get('Key') in ['P', 'B']:
                try:
                    cards = json.loads(item.get('Value', '[]'))
                    logger.info(f"  {item['Key']} карты: {cards}")
                except:
                    pass

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С API =====
def get_game_details(game_id):
    """Получает детали игры с правильными параметрами"""
    url = f"{API_BASE}/service-api/LiveFeed/GetGameZip"
    params = {
        'id': game_id,
        'country': 1,
        'marketType': 1,
        'isSubGames': 'true',
        'GroupEvents': 'true',
        'countevents': 250,
        'grMode': 4,
        'isNewBuilder': 'true'
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15, verify=False)
        if response.status_code == 200:
            data = response.json()
            if data and data.get('Success'):
                return data
            else:
                logger.warning(f"API вернул Success=false для игры {game_id}")
                return None
        else:
            logger.error(f"HTTP {response.status_code} для игры {game_id}")
            return None
    except Exception as e:
        logger.error(f"Ошибка запроса для игры {game_id}: {e}")
        return None

def extract_cards(details):
    """Извлекает карты из данных игры с защитой от ошибок"""
    if not details or not isinstance(details, dict):
        logger.warning("extract_cards: details is None или не словарь")
        return [], []
    
    try:
        value = details.get('Value', {})
        if not value:
            return [], []
            
        sc = value.get('SC', {})
        if not sc:
            return [], []
        
        player_cards = []
        banker_cards = []
        
        if 'S' in sc and isinstance(sc['S'], list):
            for item in sc['S']:
                if isinstance(item, dict):
                    key = item.get('Key')
                    if key in ['P', 'B']:
                        try:
                            cards_value = item.get('Value', '[]')
                            if cards_value:
                                cards = json.loads(cards_value)
                                if key == 'P':
                                    player_cards = cards if isinstance(cards, list) else []
                                else:
                                    banker_cards = cards if isinstance(cards, list) else []
                                logger.info(f"Найдены карты {key}: {player_cards if key=='P' else banker_cards}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Ошибка парсинга JSON для {key}: {e}")
                        except Exception as e:
                            logger.error(f"Ошибка обработки карт {key}: {e}")
        
        return player_cards, banker_cards
    except Exception as e:
        logger.error(f"Ошибка извлечения карт: {e}")
        return [], []

def parse_card(card):
    """Преобразует карту в читаемый вид"""
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
    """Вычисляет счет в баккаре"""
    if not cards or not isinstance(cards, list):
        return 0
    
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
    """Получает информацию об игре с защитой от ошибок"""
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
        'player_cards': [parse_card(c) for c in player_cards if isinstance(c, dict)],
        'banker_cards': [parse_card(c) for c in banker_cards if isinstance(c, dict)],
        'player_score': player_score,
        'banker_score': banker_score,
        'winner': winner,
        'raw_player': player_cards,
        'raw_banker': banker_cards
    }
    
    logger.info(f"Результат игры {game_id}: Player={result['player_cards']} ({player_score}), Banker={result['banker_cards']} ({banker_score})")
    return result

def format_game_message(game):
    """Форматирует сообщение об игре для Telegram"""
    if not game:
        return "Нет данных об игре"
    
    return (
        f"🎲 <b>Игра {game['game_id']}</b>\n"
        f"👤 Player: {' '.join(game['player_cards'])} = {game['player_score']}\n"
        f"🏦 Banker: {' '.join(game['banker_cards'])} = {game['banker_score']}\n"
        f"🏆 Победитель: {game['winner']}"
    )

# ===== TELEGRAM ФУНКЦИИ =====
def send_telegram_message(chat_id, text):
    """Отправляет сообщение в Telegram"""
    if not TOKEN or not chat_id:
        logger.error("TOKEN или CHAT_ID не заданы")
        return False
        
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
    """Получает обновления от Telegram"""
    if not TOKEN:
        logger.error("TOKEN не задан")
        return []
        
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
    
    # Проверяем наличие необходимых переменных
    if not TOKEN:
        logger.error("❌ TOKEN не задан! Проверьте файл .env")
        return
    
    if not CHAT_ID:
        logger.error("❌ CHAT_ID не задан! Проверьте файл .env")
        return
    
    # Проверяем токен
    try:
        response = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=10)
        me = response.json()
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
    
    # Пробуем сразу получить данные
    logger.info("\n🔍 ПРОБУЕМ ПОЛУЧИТЬ ИГРЫ СЕЙЧАС:")
    for game_id in GAME_IDS:
        game = get_game_info(game_id)
        if game:
            message = format_game_message(game)
            logger.info(f"✅ Игра {game_id}: {message}")
            send_telegram_message(CHAT_ID, message)
        else:
            logger.info(f"❌ Игра {game_id}: данных нет")
    
    if not api_working:
        logger.warning("⚠️ API игр не работает! Бот продолжит работу, но может не получать данные.")
    
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
                        msg += f"Последних отправок: {send_count}\n"
                        msg += f"API работает: {'✅' if api_working else '❌'}"
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
            
            # Автоматическая проверка каждые 10 секунд
            current_time = int(time.time())
            if current_time % 10 < 2:
                logger.info("🔄 Автоматическая проверка игр...")
                
                for game_id in GAME_IDS:
                    game = get_game_info(game_id)
                    if game:
                        # Создаем ключ состояния на основе карт
                        state_key = f"{game['player_cards']}_{game['banker_cards']}"
                        
                        if last_games.get(game_id) != state_key:
                            logger.info(f"⚡ ИЗМЕНЕНИЕ в игре {game_id}")
                            send_telegram_message(CHAT_ID, format_game_message(game))
                            last_games[game_id] = state_key
                            send_count += 1
            
            time.sleep(2)
            
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен")
            break
        except Exception as e:
            logger.error(f"Ошибка в основном цикле: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()