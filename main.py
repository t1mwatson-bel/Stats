import os
import sys
import json
import time
import logging
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Загружаем переменные окружения
load_dotenv()

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

# Маппинг рангов (масти будем определять визуально)
RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}

# ===== ФУНКЦИЯ ПОЛУЧЕНИЯ КАРТ ЧЕРЕЗ БРАУЗЕР =====
async def get_cards_from_browser(game_id):
    """Получает карты через настоящий браузер (обходит защиту)"""
    url = f"{API_BASE}/game/{game_id}"  # или правильный URL игры
    
    try:
        async with async_playwright() as p:
            # Запускаем браузер (headless=True для сервера)
            browser = await p.chromium.launch(
                headless=True,  # На сервере без графики
                args=['--no-sandbox', '--disable-setuid-sandbox']  # Важно для Linux
            )
            
            # Создаем контекст с реальными параметрами
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = await context.new_page()
            logger.info(f"🌐 Открываем страницу игры {game_id}")
            
            # Переходим на страницу
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Ждем загрузки контента
            await page.wait_for_timeout(5000)
            
            # Делаем скриншот для отладки
            await page.screenshot(path=f'debug_game_{game_id}.png')
            logger.info(f"📸 Скриншот сохранен")
            
            # Пробуем найти карты (селекторы нужно подобрать под сайт)
            player_cards = []
            banker_cards = []
            
            try:
                # Ищем карты игрока
                player_elements = await page.query_selector_all('.player-cards .card, .cards-player .card')
                for el in player_elements:
                    text = await el.text_content()
                    if text:
                        player_cards.append(text.strip())
                
                # Ищем карты банкира
                banker_elements = await page.query_selector_all('.banker-cards .card, .cards-banker .card')
                for el in banker_elements:
                    text = await el.text_content()
                    if text:
                        banker_cards.append(text.strip())
                
                logger.info(f"Найдено карт: Player={player_cards}, Banker={banker_cards}")
                
            except Exception as e:
                logger.error(f"Ошибка поиска карт: {e}")
                # Сохраняем HTML для анализа
                html = await page.content()
                with open(f'debug_game_{game_id}.html', 'w') as f:
                    f.write(html)
            
            await browser.close()
            
            # Если нашли карты через селекторы
            if player_cards or banker_cards:
                return player_cards, banker_cards
            
            # Если не нашли - возвращаем заглушку
            return [], []
            
    except Exception as e:
        logger.error(f"❌ Ошибка браузера: {e}")
        return [], []

# ===== ПАРСИНГ КАРТЫ (упрощенный) =====
def parse_card_text(card_text):
    """Парсит текст карты (например 'A♥' или '10♠')"""
    if not card_text:
        return '??'
    
    # Оставляем как есть - браузер уже дал правильные символы
    return card_text

def calculate_score_from_text(cards_text):
    """Вычисляет счет по текстовому представлению карт"""
    total = 0
    for card in cards_text:
        # Извлекаем ранг из начала строки
        rank_str = ''.join(c for c in card if not c in '♥♠♣♦')
        try:
            if rank_str in ['A', 'A♥', 'A♠', 'A♣', 'A♦']:
                total += 1
            elif rank_str in ['J', 'Q', 'K']:
                total += 0
            elif rank_str.isdigit():
                total += int(rank_str)
        except:
            pass
    return total % 10

# ===== ПОЛУЧЕНИЕ ИНФОРМАЦИИ ОБ ИГРЕ =====
async def get_game_info_browser(game_id):
    """Получает информацию об игре через браузер"""
    player_cards_text, banker_cards_text = await get_cards_from_browser(game_id)
    
    if not player_cards_text and not banker_cards_text:
        return None
    
    # Преобразуем в читаемый вид
    player_cards = [parse_card_text(c) for c in player_cards_text]
    banker_cards = [parse_card_text(c) for c in banker_cards_text]
    
    player_score = calculate_score_from_text(player_cards)
    banker_score = calculate_score_from_text(banker_cards)
    
    winner = 'Tie' if player_score == banker_score else 'Player' if player_score > banker_score else 'Banker'
    
    result = {
        'game_id': game_id,
        'player_cards': player_cards,
        'banker_cards': banker_cards,
        'player_score': player_score,
        'banker_score': banker_score,
        'winner': winner
    }
    
    logger.info(f"✅ Результат: Player={player_cards} ({player_score}), Banker={banker_cards} ({banker_score})")
    return result

def format_game_message(game):
    if not game:
        return "Нет данных"
    
    return (
        f"🎲 <b>Игра {game['game_id']}</b>\n"
        f"👤 Player: {' '.join(game['player_cards'])} = {game['player_score']}\n"
        f"🏦 Banker: {' '.join(game['banker_cards'])} = {game['banker_score']}\n"
        f"🏆 Победитель: {game['winner']}"
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
            logger.info(f"✅ Сообщение отправлено в {chat_id}")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
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
        logger.error(f"❌ Ошибка getUpdates: {e}")
    return []

# ===== ОСНОВНОЙ ЦИКЛ =====
async def main_async():
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК БОТА С БРАУЗЕРНОЙ АВТОМАТИЗАЦИЕЙ")
    logger.info("=" * 60)
    
    # Проверка токена
    if not TOKEN or not CHAT_ID:
        logger.error("❌ TOKEN или CHAT_ID не заданы")
        return
    
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
    
    # ID игр для отслеживания (можно динамически обновлять)
    tracked_games = [697705521, 697704425]
    game_states = {}
    send_count = 0
    last_update_id = 0
    
    logger.info(f"\n🎮 Отслеживаем игры: {tracked_games}")
    logger.info("✅ Бот запущен и готов к работе!")
    
    while True:
        try:
            # Проверяем игры
            for game_id in tracked_games:
                logger.info(f"\n🔍 Проверка игры {game_id}...")
                game = await get_game_info_browser(game_id)
                
                if game:
                    state_key = f"{game['player_cards']}_{game['banker_cards']}"
                    
                    if game_id not in game_states:
                        # Новая игра
                        game_states[game_id] = state_key
                        send_telegram_message(CHAT_ID, f"🆕 Новая игра!\n\n{format_game_message(game)}")
                        send_count += 1
                        logger.info(f"🆕 Отправлено новое сообщение")
                    
                    elif game_states[game_id] != state_key:
                        # Изменение
                        game_states[game_id] = state_key
                        send_telegram_message(CHAT_ID, f"⚡ Изменение!\n\n{format_game_message(game)}")
                        send_count += 1
                        logger.info(f"⚡ Отправлено обновление")
                
                # Небольшая задержка между проверками игр
                await asyncio.sleep(5)
            
            # Обработка команд
            updates = get_updates(last_update_id + 1)
            for update in updates:
                last_update_id = update['update_id']
                if 'message' in update and 'text' in update['message']:
                    chat_id = update['message']['chat']['id']
                    text = update['message']['text']
                    
                    if text == '/status':
                        msg = f"📊 Статус:\nИгр: {len(tracked_games)}\nОтправок: {send_count}"
                        send_telegram_message(chat_id, msg)
            
            # Пауза перед следующим циклом
            logger.info("💤 Ожидание 30 секунд...")
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            await asyncio.sleep(10)

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()