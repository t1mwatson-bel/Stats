import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
from collections import defaultdict
import urllib3

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
TOKEN = os.getenv("TOKEN", "8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU")
API_BASE = "https://1xlite-7636770.bar"
GAME_IDS = [697705521, 697704425]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://1xlite-7636770.bar/',
}

RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}

# ===== ИМПОРТ TELEGRAM (ПРОСТАЯ ВЕРСИЯ) =====
try:
    import telegram
    from telegram.ext import Updater, CommandHandler
    logger.info(f"Telegram библиотека версии {telegram.__version__} загружена")
except ImportError as e:
    logger.error(f"Ошибка импорта telegram: {e}")
    sys.exit(1)

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С API =====
def get_game_details(game_id):
    """Получает детали игры из API"""
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
    """Извлекает карты из ответа API"""
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
                        except:
                            pass
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
    
    # Маппинг рангов
    rank_map = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
    
    if rank in rank_map:
        rank_str = rank_map[rank]
    elif rank and 2 <= rank <= 10:
        rank_str = str(rank)
    else:
        rank_str = '?'
    
    # Маппинг мастей (временный)
    suit_map = {1: '♥️', 2: '♠️', 3: '♣️', 4: '♦️'}
    suit_str = suit_map.get(suit, '?') if suit != 0 else '?'
    
    return f"{rank_str}{suit_str}"

def calculate_score(cards):
    """Вычисляет очки в баккаре"""
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
    
    return {
        'game_id': game_id,
        'player_cards': [parse_card(c) for c in player_cards],
        'banker_cards': [parse_card(c) for c in banker_cards],
        'player_score': player_score,
        'banker_score': banker_score,
        'winner': 'Player' if player_score > banker_score else 'Banker' if banker_score > player_score else 'Tie'
    }

# ===== TELEGRAM ОБРАБОТЧИКИ =====
def start(update, context):
    """Обработчик команды /start"""
    chat_id = update.effective_chat.id
    logger.info(f"Команда /start от {chat_id}")
    
    update.message.reply_text(
        "🤖 Бот для баккары запущен!\n\n"
        "Команды:\n"
        "/check - проверить игры\n"
        "/help - помощь"
    )

def check(update, context):
    """Проверка игр"""
    chat_id = update.effective_chat.id
    logger.info(f"Команда /check от {chat_id}")
    
    update.message.reply_text("🔍 Проверяю игры...")
    
    for game_id in GAME_IDS:
        game = get_game_info(game_id)
        if game:
            msg = (
                f"🎲 **Игра {game_id}**\n"
                f"Player: {' '.join(game['player_cards'])} = {game['player_score']}\n"
                f"Banker: {' '.join(game['banker_cards'])} = {game['banker_score']}\n"
                f"Победитель: {game['winner']}"
            )
            update.message.reply_text(msg)
        else:
            update.message.reply_text(f"❌ Нет данных для игры {game_id}")

def help_command(update, context):
    """Помощь"""
    update.message.reply_text(
        "/start - запуск\n"
        "/check - проверить игры\n"
        "/help - помощь"
    )

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
def main():
    """Запуск бота"""
    logger.info("🚀 Запуск бота...")
    logger.info(f"Токен: {TOKEN[:10]}...")
    
    try:
        # Создаем бота (простая версия)
        bot = telegram.Bot(token=TOKEN)
        logger.info(f"Бот создан: {bot.get_me().username}")
        
        # Создаем Updater
        updater = Updater(token=TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # Добавляем обработчики
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("check", check))
        dp.add_handler(CommandHandler("help", help_command))
        
        # Запускаем
        logger.info("Бот запускает polling...")
        updater.start_polling()
        logger.info("✅ Бот успешно запущен!")
        
        # Работаем
        updater.idle()
        
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()