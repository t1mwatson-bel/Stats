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

# ===== ПОИСК НОВЫХ ИГР =====
def find_new_games(know_games):
    """Ищет новые игры, которых еще нет в отслеживаемых"""
    url = f"{API_BASE}/service-api/LiveFeed/Get1x2_VZip"
    params = {
        'sports': 236,
        'count': 50,
        'mode': 4,
        'top': 'true',
        'partner': 5
    }
    
    try:
        logger.debug("🔍 Поиск новых игр...")
        response = requests.get(url, headers=HEADERS, params=params, timeout=10, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            if data and data.get('Success'):
                games = data.get('Value', [])
                new_games = []
                
                for game in games:
                    if isinstance(game, dict):
                        game_id = game.get('I')
                        if game_id and game_id not in know_games:
                            new_games.append(game_id)
                            logger.info(f"🆕 Найдена НОВАЯ игра: {game_id}")
                
                return new_games
    except Exception as e:
        logger.debug(f"Ошибка поиска новых игр: {e}")
    
    return []

# ===== ПРОВЕРКА ИГРЫ =====
def get_game_details(game_id):
    """Получает детали игры"""
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
    except Exception as e:
        logger.debug(f"Ошибка запроса для игры {game_id}: {e}")
    
    return None

def extract_cards(details):
    """Извлекает карты из данных игры"""
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
                        except:
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
    """Получает информацию об игре"""
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
        'has_cards': len(player_cards) > 0 or len(banker_cards) > 0
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
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке: {e}")
    
    return False

def get_updates(offset=None):
    """Получает обновления от Telegram"""
    if not TOKEN:
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
    logger.info("🚀 ЗАПУСК БОТА С ПОИСКОМ НОВЫХ ИГР")
    logger.info("=" * 60)
    
    # Проверяем токен
    if not TOKEN or not CHAT_ID:
        logger.error("❌ TOKEN или CHAT_ID не заданы")
        return
    
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
    
    # Множество отслеживаемых игр
    tracked_games = set()
    game_states = {}  # Для отслеживания изменений
    send_count = 0
    last_update_id = 0
    last_new_game_check = 0
    
    logger.info("\n✅ Бот запущен и ищет новые игры!")
    logger.info("=" * 60)
    
    while True:
        try:
            current_time = time.time()
            
            # 1. ПОИСК НОВЫХ ИГР (каждые 30 секунд)
            if current_time - last_new_game_check > 30:
                logger.info("🔍 Проверка новых игр...")
                new_games = find_new_games(tracked_games)
                
                for game_id in new_games:
                    tracked_games.add(game_id)
                    logger.info(f"➕ Игра {game_id} добавлена в отслеживание")
                    
                    # Сразу проверяем, есть ли карты
                    game_info = get_game_info(game_id)
                    if game_info and game_info['has_cards']:
                        msg = f"🆕 <b>Новая игра!</b>\n\n{format_game_message(game_info)}"
                        send_telegram_message(CHAT_ID, msg)
                        game_states[game_id] = f"{game_info['player_cards']}_{game_info['banker_cards']}"
                        send_count += 1
                
                last_new_game_check = current_time
            
            # 2. ПРОВЕРКА АКТИВНЫХ ИГР (каждые 5 секунд)
            if int(current_time) % 5 == 0:
                for game_id in list(tracked_games):  # Используем list для безопасного удаления
                    game_info = get_game_info(game_id)
                    
                    if not game_info or not game_info['has_cards']:
                        # Игра больше не имеет карт - удаляем из отслеживания
                        if game_id in tracked_games:
                            tracked_games.remove(game_id)
                            if game_id in game_states:
                                del game_states[game_id]
                            logger.info(f"➖ Игра {game_id} удалена из отслеживания (завершена)")
                        continue
                    
                    # Проверяем изменения
                    current_state = f"{game_info['player_cards']}_{game_info['banker_cards']}"
                    if game_id not in game_states:
                        # Новая игра с картами
                        game_states[game_id] = current_state
                        msg = f"🆕 <b>Новая игра!</b>\n\n{format_game_message(game_info)}"
                        send_telegram_message(CHAT_ID, msg)
                        send_count += 1
                    elif game_states[game_id] != current_state:
                        # Изменение в игре
                        game_states[game_id] = current_state
                        msg = f"⚡ <b>Изменение в игре {game_id}</b>\n\n{format_game_message(game_info)}"
                        send_telegram_message(CHAT_ID, msg)
                        send_count += 1
            
            # 3. ОБРАБОТКА КОМАНД
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
                            "/status - статус бота\n"
                            "/games - список отслеживаемых игр\n"
                            "/check - принудительная проверка"
                        )
                    
                    elif text == '/status':
                        msg = f"📊 Статус бота:\n"
                        msg += f"🎮 Отслеживается игр: {len(tracked_games)}\n"
                        msg += f"📨 Отправлено сообщений: {send_count}\n"
                        send_telegram_message(chat_id, msg)
                    
                    elif text == '/games':
                        if tracked_games:
                            msg = f"🎮 Отслеживаемые игры ({len(tracked_games)}):\n"
                            for gid in list(tracked_games)[:10]:
                                msg += f"• {gid}\n"
                        else:
                            msg = "❌ Нет отслеживаемых игр"
                        send_telegram_message(chat_id, msg)
                    
                    elif text == '/check':
                        send_telegram_message(chat_id, "🔍 Принудительная проверка...")
                        # Просто запускаем поиск новых игр сейчас
                        new_games = find_new_games(tracked_games)
                        if new_games:
                            send_telegram_message(chat_id, f"✅ Найдено новых игр: {len(new_games)}")
                        else:
                            send_telegram_message(chat_id, "❌ Новых игр не найдено")
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в основном цикле: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()