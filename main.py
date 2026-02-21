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
CHAT_ID = os.getenv("CHAT_ID")

# Запасные ID на случай, если API не отдаст список
FALLBACK_GAME_IDS = [697705521, 697704425]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': f'{API_BASE}/',
    'Origin': API_BASE,
}

# Маппинг рангов и мастей
RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
SUIT_MAP = {1: '♥️', 2: '♠️', 3: '♣️', 4: '♦️'}

# ===== ПОЛУЧЕНИЕ СПИСКА АКТИВНЫХ ИГР =====
def get_live_games():
    """Получает список текущих игр в баккару"""
    url = f"{API_BASE}/service-api/LiveFeed/Get1x2_VZip"
    params = {
        'sports': 236,  # ID баккары (может отличаться, попробуйте 235, 237 если не работает)
        'count': 30,    # Количество игр
        'mode': 4,
        'top': 'true',
        'partner': 5
    }
    
    try:
        logger.info("🔍 Получаем список активных игр...")
        response = requests.get(url, headers=HEADERS, params=params, timeout=15, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            if data and data.get('Success'):
                games = data.get('Value', [])
                game_ids = []
                for game in games:
                    if isinstance(game, dict):
                        game_id = game.get('I')
                        if game_id:
                            game_ids.append(game_id)
                            logger.info(f"  ✅ Найдена игра ID: {game_id}")
                return game_ids
            else:
                logger.warning("⚠️ API вернул Success=false при получении списка игр")
                return []
        else:
            logger.error(f"❌ Ошибка HTTP {response.status_code} при получении списка игр")
            return []
    except Exception as e:
        logger.error(f"❌ Ошибка при получении списка игр: {e}")
        return []

def get_active_game_ids():
    """Возвращает список актуальных ID игр"""
    game_ids = get_live_games()
    if not game_ids:
        logger.warning("⚠️ Не удалось получить список игр, использую запасные ID")
        return FALLBACK_GAME_IDS
    return game_ids[:10]  # Берем первые 10 игр

# ===== ПРЯМАЯ ПРОВЕРКА API =====
def test_api_connection():
    logger.info("=" * 50)
    logger.info("ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЯ К API")
    logger.info("=" * 50)
    
    success_count = 0
    game_ids = get_active_game_ids()[:3]  # Проверяем первые 3 игры
    
    # Проверка основного домена
    try:
        response = requests.get(API_BASE, timeout=5, verify=False)
        logger.info(f"Основной домен: {response.status_code}")
    except Exception as e:
        logger.error(f"Основной домен недоступен: {e}")
    
    if not game_ids:
        logger.error("❌ Нет ID игр для проверки")
        return False
    
    # Проверка данных для игр
    for game_id in game_ids:
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
                    logger.warning(f"⚠️ API вернул Success=false для игры {game_id}")
            else:
                logger.error(f"❌ Ошибка HTTP {response.status_code} для игры {game_id}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при тестировании игры {game_id}: {e}")
    
    if success_count == 0:
        logger.error("❌ НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ НИ ПО ОДНОЙ ИГРЕ")
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
                logger.debug(f"API вернул Success=false для игры {game_id}")
                return None
        else:
            logger.debug(f"HTTP {response.status_code} для игры {game_id}")
            return None
    except Exception as e:
        logger.debug(f"Ошибка запроса для игры {game_id}: {e}")
        return None

def extract_cards(details):
    """Извлекает карты из данных игры с защитой от ошибок"""
    if not details or not isinstance(details, dict):
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
                                logger.debug(f"Найдены карты {key}: {player_cards if key=='P' else banker_cards}")
                        except json.JSONDecodeError:
                            pass
                        except Exception:
                            pass
        
        return player_cards, banker_cards
    except Exception:
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
    details = get_game_details(game_id)
    
    if not details:
        return None
    
    player_cards, banker_cards = extract_cards(details)
    
    if not player_cards and not banker_cards:
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
            logger.info(f"✅ Сообщение отправлено в чат {chat_id}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке: {e}")
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
        logger.error(f"❌ Ошибка getUpdates: {e}")
    return []

# ===== ОСНОВНОЙ ЦИКЛ =====
def main():
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК БОТА С ДИНАМИЧЕСКИМ ПОИСКОМ ИГР")
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
    
    # Получаем актуальные игры
    logger.info("\n🔍 ПОЛУЧАЕМ СПИСОК АКТИВНЫХ ИГР...")
    active_games = get_active_game_ids()
    
    if active_games and active_games != FALLBACK_GAME_IDS:
        logger.info(f"✅ Найдено активных игр: {len(active_games)}")
        logger.info(f"📋 ID первых 5 игр: {active_games[:5]}")
    else:
        logger.warning("⚠️ Используются запасные ID игр")
    
    # Тестируем API игры
    logger.info("\n🔍 ПРОВЕРКА API ИГР...")
    api_working = test_api_connection()
    
    # Пробуем сразу получить данные
    logger.info("\n🔍 ПРОБУЕМ ПОЛУЧИТЬ ИГРЫ ПРЯМО СЕЙЧАС:")
    games_found = 0
    for game_id in active_games[:5]:  # Проверяем первые 5 игр
        game = get_game_info(game_id)
        if game:
            message = format_game_message(game)
            logger.info(f"✅ Игра {game_id}: {message}")
            send_telegram_message(CHAT_ID, message)
            games_found += 1
            time.sleep(1)  # Небольшая задержка между отправками
        else:
            logger.info(f"❌ Игра {game_id}: данных нет")
    
    if games_found == 0:
        logger.warning("⚠️ Нет активных игр с картами в данный момент")
    
    last_update_id = 0
    last_games = {}
    send_count = 0
    last_games_refresh = 0
    
    logger.info("\n✅ Бот запущен и готов к работе!")
    logger.info("=" * 60)
    
    while True:
        try:
            # Обновляем список игр каждые 5 минут
            current_time = time.time()
            if current_time - last_games_refresh > 300:  # 300 секунд = 5 минут
                logger.info("🔄 Обновление списка активных игр...")
                new_games = get_active_game_ids()
                if new_games and new_games != FALLBACK_GAME_IDS:
                    active_games = new_games
                    logger.info(f"✅ Список обновлен. Найдено игр: {len(active_games)}")
                last_games_refresh = current_time
            
            # Обработка команд из Telegram
            updates = get_updates(last_update_id + 1)
            
            for update in updates:
                last_update_id = update['update_id']
                
                if 'message' in update and 'text' in update['message']:
                    chat_id = update['message']['chat']['id']
                    text = update['message']['text']
                    
                    logger.info(f"📨 Команда от {chat_id}: {text}")
                    
                    if text == '/start':
                        send_telegram_message(chat_id, 
                            "🤖 Бот для баккары запущен!\n\n"
                            "Команды:\n"
                            "/check - проверить игры сейчас\n"
                            "/test - тест API\n"
                            "/status - статус бота\n"
                            "/games - список активных игр"
                        )
                    
                    elif text == '/games':
                        msg = f"🎮 Активные игры ({len(active_games)}):\n"
                        for gid in active_games[:10]:
                            msg += f"• {gid}\n"
                        send_telegram_message(chat_id, msg)
                    
                    elif text == '/test':
                        send_telegram_message(chat_id, "🔍 Тестирую подключение к API...")
                        if test_api_connection():
                            send_telegram_message(chat_id, "✅ API работает!")
                        else:
                            send_telegram_message(chat_id, "❌ API не отвечает!")
                    
                    elif text == '/status':
                        msg = f"📊 Статус бота:\n"
                        msg += f"🎮 Активных игр: {len(active_games)}\n"
                        msg += f"📨 Отправлено сообщений: {send_count}\n"
                        msg += f"🔌 API работает: {'✅' if api_working else '❌'}"
                        send_telegram_message(chat_id, msg)
                    
                    elif text == '/check':
                        send_telegram_message(chat_id, "🔍 Проверяю игры...")
                        found = 0
                        for game_id in active_games[:5]:
                            game = get_game_info(game_id)
                            if game:
                                send_telegram_message(chat_id, format_game_message(game))
                                found += 1
                                time.sleep(1)
                        if found == 0:
                            send_telegram_message(chat_id, "❌ Нет данных по играм")
                        else:
                            send_telegram_message(chat_id, f"✅ Найдено игр: {found}")
                            send_count += found
            
            # Автоматическая проверка каждые 10 секунд
            if int(current_time) % 10 < 2:
                logger.info("🔄 Автоматическая проверка игр...")
                
                for game_id in active_games[:5]:  # Проверяем первые 5 игр
                    game = get_game_info(game_id)
                    if game:
                        # Создаем ключ состояния на основе карт
                        state_key = f"{game['player_cards']}_{game['banker_cards']}"
                        
                        if last_games.get(game_id) != state_key:
                            logger.info(f"⚡ ИЗМЕНЕНИЕ в игре {game_id}")
                            send_telegram_message(CHAT_ID, format_game_message(game))
                            last_games[game_id] = state_key
                            send_count += 1
                            time.sleep(1)  # Задержка между отправками
            
            time.sleep(2)
            
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в основном цикле: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()