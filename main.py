import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
from collections import defaultdict
import urllib3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Отключаем предупреждения о SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== НАСТРОЙКА ЛОГИРОВАНИЯ =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# ===== ПЕРЕМЕННЫЕ =====
TOKEN = os.getenv("TOKEN", "8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU")
API_BASE = "https://1xlite-7636770.bar"
GAME_IDS = [697705521, 697704425]  # ID игр для отслеживания

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://1xlite-7636770.bar/',
}

RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
game_suit_mappings = {}

# ===== ФУНКЦИИ РАБОТЫ С API =====
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
    
    logger.info(f"Запрос к API для игры {game_id}")
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15, verify=False)
        logger.info(f"Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Успешно получены данные для игры {game_id}")
            return data
        else:
            logger.error(f"Ошибка HTTP {response.status_code} для игры {game_id}")
            logger.error(f"Ответ: {response.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"Таймаут при запросе игры {game_id}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"Ошибка подключения для игры {game_id}")
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка для игры {game_id}: {e}")
        return None

def extract_cards_from_api(details):
    """Извлекает карты из API ответа"""
    if not details:
        logger.error("Нет данных для извлечения карт")
        return [], []
    
    try:
        value = details.get('Value', {})
        sc = value.get('SC', {})
        
        logger.info(f"Структура SC: {list(sc.keys())}")
        
        player_cards = []
        banker_cards = []
        
        if 'S' in sc:
            logger.info(f"Найдено {len(sc['S'])} элементов в S")
            for item in sc['S']:
                if isinstance(item, dict):
                    key = item.get('Key')
                    logger.info(f"Найден ключ: {key}")
                    
                    if key in ['P', 'B']:
                        try:
                            cards_value = item.get('Value', '[]')
                            cards = json.loads(cards_value)
                            logger.info(f"Карты {key}: {cards}")
                            
                            if key == 'P':
                                player_cards = cards
                            else:
                                banker_cards = cards
                        except json.JSONDecodeError as e:
                            logger.error(f"Ошибка парсинга JSON для {key}: {e}")
        
        logger.info(f"Извлечено карт: Player={len(player_cards)}, Banker={len(banker_cards)}")
        return player_cards, banker_cards
        
    except Exception as e:
        logger.error(f"Ошибка в extract_cards_from_api: {e}")
        return [], []

def analyze_suit_mapping(player_cards, banker_cards, game_id):
    """Создает маппинг мастей"""
    if game_id in game_suit_mappings:
        logger.info(f"Использую существующий маппинг для игры {game_id}")
        return game_suit_mappings[game_id]
    
    logger.info(f"Создаю новый маппинг для игры {game_id}")
    
    all_cards = player_cards + banker_cards
    suit_stats = defaultdict(lambda: {'count': 0, 'rank_sum': 0})
    
    for card in all_cards:
        if isinstance(card, dict):
            suit_code = card.get('S')
            rank = card.get('R')
            if suit_code and rank and suit_code != 0:
                suit_stats[suit_code]['count'] += 1
                suit_stats[suit_code]['rank_sum'] += rank
    
    logger.info(f"Статистика мастей: {dict(suit_stats)}")
    
    # Простой маппинг (для теста)
    mapping = {1: '♥️', 2: '♠️', 3: '♣️', 4: '♦️'}
    game_suit_mappings[game_id] = mapping
    logger.info(f"Маппинг сохранен: {mapping}")
    
    return mapping

def parse_card(card_dict, game_id):
    """Преобразует карту в строку"""
    if not isinstance(card_dict, dict):
        return '??'
    
    rank_num = card_dict.get('R')
    suit_code = card_dict.get('S', 0)
    
    # Ранг
    if rank_num in RANK_MAP:
        rank = RANK_MAP[rank_num]
    elif rank_num and 2 <= rank_num <= 10:
        rank = str(rank_num)
    else:
        rank = '?'
    
    # Масть
    if suit_code == 0:
        suit = '?'
    else:
        mapping = game_suit_mappings.get(game_id, {})
        suit = mapping.get(suit_code, f'?{suit_code}')
    
    return f"{rank}{suit}"

def calculate_score(cards):
    """Вычисляет очки"""
    total = 0
    for card in cards:
        if isinstance(card, dict):
            rank = card.get('R', 0)
            if rank in [1, 14]:
                total += 1
            elif rank in [11, 12, 13]:
                total += 0
            elif rank and 2 <= rank <= 10:
                total += rank
    return total % 10

def determine_winner(player_score, banker_score):
    """Определяет победителя"""
    if player_score > banker_score:
        return 'Player'
    elif banker_score > player_score:
        return 'Banker'
    else:
        return 'Tie'

def get_game_data(game_id, game_number):
    """Получает данные игры"""
    logger.info(f"Получение данных для игры {game_id} (номер {game_number})")
    
    details = get_game_details(game_id)
    if not details:
        logger.error(f"Не удалось получить данные для игры {game_id}")
        return None
    
    player_cards, banker_cards = extract_cards_from_api(details)
    
    if not player_cards and not banker_cards:
        logger.warning(f"Нет карт для игры {game_id}")
        return None
    
    analyze_suit_mapping(player_cards, banker_cards, game_id)
    
    player_score = calculate_score(player_cards)
    banker_score = calculate_score(banker_cards)
    winner = determine_winner(player_score, banker_score)
    
    player_cards_str = [parse_card(c, game_id) for c in player_cards]
    banker_cards_str = [parse_card(c, game_id) for c in banker_cards]
    
    result = {
        'game_number': game_number,
        'game_id': game_id,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'player_cards': player_cards_str,
        'banker_cards': banker_cards_str,
        'player_score': player_score,
        'banker_score': banker_score,
        'winner': winner
    }
    
    logger.info(f"Результат игры {game_id}: Player={player_cards_str}, Banker={banker_cards_str}")
    return result

# ===== TELEGRAM BOT =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_id = update.effective_chat.id
    logger.info(f"Получена команда /start от чата {chat_id}")
    
    await update.message.reply_text(
        "🤖 Бот для отслеживания баккары запущен!\n\n"
        f"Отслеживаю игры: {GAME_IDS}\n\n"
        "Команды:\n"
        "/status - проверить статус\n"
        "/force - принудительно проверить игры"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса"""
    chat_id = update.effective_chat.id
    logger.info(f"Запрос статуса от чата {chat_id}")
    
    msg = f"🎲 **Текущий статус**\n\n"
    msg += f"Отслеживается игр: {len(GAME_IDS)}\n\n"
    
    for game_id in GAME_IDS:
        msg += f"**Игра {game_id}**\n"
        mapping = game_suit_mappings.get(game_id, {})
        msg += f"Маппинг: {mapping}\n"
        
        # Пробуем получить данные
        data = get_game_data(game_id, 0)
        if data:
            msg += f"Player: {data['player_cards']}\n"
            msg += f"Banker: {data['banker_cards']}\n"
            msg += f"Счет: {data['player_score']}:{data['banker_score']}\n"
        else:
            msg += "❌ Нет данных\n"
        msg += "\n"
    
    await update.message.reply_text(msg)

async def force_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительная проверка"""
    chat_id = update.effective_chat.id
    logger.info(f"Принудительная проверка от чата {chat_id}")
    
    await update.message.reply_text("🔍 Проверяю игры...")
    
    for game_id in GAME_IDS:
        data = get_game_data(game_id, 0)
        if data:
            msg = (
                f"🎲 **Игра {game_id}**\n"
                f"Player: {' '.join(data['player_cards'])} = {data['player_score']}\n"
                f"Banker: {' '.join(data['banker_cards'])} = {data['banker_score']}\n"
                f"Победитель: {data['winner']}"
            )
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text(f"❌ Нет данных для игры {game_id}")

# ===== ФОНОВЫЙ МОНИТОРИНГ =====
async def monitor_games(context: ContextTypes.DEFAULT_TYPE):
    """Периодическая проверка игр"""
    chat_id = context.job.chat_id
    logger.info(f"Фоновая проверка игр для чата {chat_id}")
    
    for game_id in GAME_IDS:
        data = get_game_data(game_id, 0)
        if data and data['player_cards']:  # Если есть карты
            msg = (
                f"🎲 **Новое обновление игры {game_id}**\n"
                f"Player: {' '.join(data['player_cards'])} = {data['player_score']}\n"
                f"Banker: {' '.join(data['banker_cards'])} = {data['banker_score']}"
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg)
                logger.info(f"Отправлено обновление для игры {game_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения: {e}")

# ===== ЗАПУСК =====
def main():
    """Главная функция"""
    logger.info("🚀 Запуск бота...")
    logger.info(f"Токен: {TOKEN[:5]}...{TOKEN[-5:]}")
    logger.info(f"API_BASE: {API_BASE}")
    logger.info(f"GAME_IDS: {GAME_IDS}")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("force", force_check))
    
    # Запускаем
    logger.info("Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()