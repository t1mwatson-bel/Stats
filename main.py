import os
import json
import logging
import asyncio
from collections import deque
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx
import re

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = "6338351608:AAGMV_lCJvQnwnnVTTBmtqdT3SHhp9iy1zQ"
SOURCE_CHAT_ID = -1001471933679  # Канал-источник
TARGET_CHAT_ID = -1003469691743  # Канал-зеркало
PREDICTION_CHANNEL_ID = -1003252757578  # ОТДЕЛЬНЫЙ КАНАЛ ДЛЯ ПРОГНОЗОВ (ЗАМЕНИ НА СВОЙ!)

# Файлы данных
MESSAGE_MAP_FILE = 'message_map.json'
CYCLE_STATS_FILE = 'cycle_stats.json'
ROLLING_STATS_FILE = 'rolling_stats.json'
PREDICTIONS_HISTORY_FILE = 'predictions_history.json'

# Параметры анализа
CYCLE_LENGTH = 1440
ROLLING_WINDOW = 50
MIN_GAMES_FOR_PREDICTION = 10

# Режим предсказаний
PREDICTION_MODE = "alternate"  # "most_common", "alternate", "rarest"
last_prediction_type = "most_common"  # Для чередования

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ГЛОБАЛЬНЫЕ КЭШИ ===
game_history = deque(maxlen=1000)
cycle_stats = {}
rolling_suit_counts = {'♣': 0, '♦': 0, '♥': 0, '♠': 0}
predictions_history = {}  # История предсказаний: game_num -> prediction_data


# === ЗАГРУЗКА/СОХРАНЕНИЕ ===
def load_message_map():
    """Загрузка маппинга сообщений"""
    if os.path.exists(MESSAGE_MAP_FILE):
        try:
            with open(MESSAGE_MAP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {MESSAGE_MAP_FILE}: {e}")
    return {}


def save_message_map(data):
    """Сохранение маппинга сообщений"""
    try:
        with open(MESSAGE_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {MESSAGE_MAP_FILE}: {e}")


def load_analytics_data():
    """Загрузка аналитических данных"""
    global cycle_stats, rolling_suit_counts, game_history, predictions_history

    # Загружаем статистику циклов
    try:
        if os.path.exists(CYCLE_STATS_FILE):
            with open(CYCLE_STATS_FILE, 'r', encoding='utf-8') as f:
                cycle_stats.update(json.load(f))
    except Exception as e:
        logger.error(f"Ошибка загрузки {CYCLE_STATS_FILE}: {e}")

    # Загружаем rolling статистику
    try:
        if os.path.exists(ROLLING_STATS_FILE):
            with open(ROLLING_STATS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                rolling_suit_counts.update(data.get('counts', {'♣': 0, '♦': 0, '♥': 0, '♠': 0}))
                history = data.get('games', [])
                game_history = deque(history[-1000:], maxlen=1000)
    except Exception as e:
        logger.error(f"Ошибка загрузки {ROLLING_STATS_FILE}: {e}")

    # Загружаем историю предсказаний
    try:
        if os.path.exists(PREDICTIONS_HISTORY_FILE):
            with open(PREDICTIONS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                predictions_history.update(json.load(f))
    except Exception as e:
        logger.error(f"Ошибка загрузки {PREDICTIONS_HISTORY_FILE}: {e}")


def save_analytics_data():
    """Сохранение аналитических данных"""
    try:
        with open(CYCLE_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(cycle_stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {CYCLE_STATS_FILE}: {e}")

    try:
        with open(ROLLING_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'counts': rolling_suit_counts,
                'games': list(game_history)[-1000:]
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {ROLLING_STATS_FILE}: {e}")

    try:
        with open(PREDICTIONS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(predictions_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {PREDICTIONS_HISTORY_FILE}: {e}")


# === ✅ ФУНКЦИИ ЗЕРКАЛИРОВАНИЯ ===
def is_32_outcome(text: str) -> bool:
    """Проверяет, является ли сообщение исходом 3/2 (игрок=3 карты, банкир=2)."""
    if '👈' in text or '👉' in text:
        return False

    parts = []
    start = 0
    while True:
        open_idx = text.find('(', start)
        if open_idx == -1:
            break
        close_idx = text.find(')', open_idx)
        if close_idx == -1:
            break
        parts.append(text[open_idx + 1:close_idx])
        start = close_idx + 1

    if len(parts) != 2:
        return False

    player_str = parts[0]
    banker_str = parts[1]

    player_count = sum(1 for ch in player_str if ch in '♣♦♥♠')
    banker_count = sum(1 for ch in banker_str if ch in '♣♦♥♠')

    return player_count == 3 and banker_count == 2


def add_32_indicator(text: str) -> str:
    """Добавляет 🟩 только если это финальное сообщение (без 👉/👈)"""
    if '👈' in text or '👉' in text:
        return text
    if is_32_outcome(text):
        return text + " 🟩"
    return text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=0.5, max=3),
    retry=retry_if_exception_type((httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException))
)
async def safe_send_message(bot, chat_id, text):
    """Безопасная отправка сообщения с повторами"""
    return await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=0.5, max=3),
    retry=retry_if_exception_type((httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException))
)
async def safe_edit_message(bot, chat_id, message_id, text):
    """Безопасное редактирование сообщения с повторами"""
    try:
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
    except Exception as e:
        if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
            # Если сообщение не найдено для редактирования — отправляем новое
            return await safe_send_message(bot, chat_id, text)
        raise


# === 🔍 ФУНКЦИИ АНАЛИЗА ===
def extract_suits(text: str) -> list[str]:
    """Извлекает масти из текста"""
    return [c for c in text if c in '♣♦♥♠']


def parse_game_data(text: str, message_id: int) -> dict | None:
    """Парсит ТОЛЬКО финальные результаты (без 👈/👉)"""

    # Пропускаем промежуточные результаты
    if '👈' in text or '👉' in text:
        return None

    # Извлекаем номер игры
    game_num = None
    match = re.search(r'#N(\d+)', text)
    if match:
        game_num = int(match.group(1))
    else:
        match = re.search(r'^\s*(\d+)', text)
        if match:
            game_num = int(match.group(1))

    if game_num is None:
        return None

    # Извлекаем содержимое скобок
    parts = []
    start = 0
    while True:
        open_idx = text.find('(', start)
        if open_idx == -1:
            break
        close_idx = text.find(')', open_idx)
        if close_idx == -1:
            break
        content = text[open_idx + 1:close_idx]
        parts.append(content)
        start = close_idx + 1

    if len(parts) < 2:
        return None

    # Извлекаем масти
    player_suits = [c for c in parts[0] if c in '♣♦♥♠']
    banker_suits = [c for c in parts[1] if c in '♣♦♥♠']

    if not player_suits and not banker_suits:
        return None

    is_32 = (len(player_suits) == 3 and len(banker_suits) == 2)
    has_natural = ('#R' in text) or ('#T6' in text) or ('#T7' in text)

    return {
        'game_num': game_num,
        'player_suits': player_suits,
        'banker_suits': banker_suits,
        'is_32': is_32,
        'has_natural': has_natural,
        'message_id': message_id,
        'raw_text': text[:100]
    }


def update_cycle_stats(game_data: dict):
    """Обновление статистики по позициям в цикле"""
    pos = ((game_data['game_num'] - 1) % CYCLE_LENGTH) + 1
    pos_key = str(pos)

    if pos_key not in cycle_stats:
        cycle_stats[pos_key] = {'♣': 0, '♦': 0, '♥': 0, '♠': 0, 'total': 0}

    stats = cycle_stats[pos_key]
    for suit in game_data['player_suits'] + game_data['banker_suits']:
        stats[suit] = stats.get(suit, 0) + 1
    stats['total'] += 1


def update_rolling_stats(game_data: dict):
    """Обновление rolling статистики"""
    global rolling_suit_counts

    # Удаляем старые данные
    if len(game_history) >= ROLLING_WINDOW:
        old_game = game_history[0]
        for suit in old_game['player_suits'] + old_game['banker_suits']:
            rolling_suit_counts[suit] = max(0, rolling_suit_counts[suit] - 1)

    # Добавляем новые данные
    for suit in game_data['player_suits'] + game_data['banker_suits']:
        rolling_suit_counts[suit] = rolling_suit_counts.get(suit, 0) + 1

    game_history.append(game_data)


# === 🎯 СИСТЕМА ПРЕДСКАЗАНИЙ ===
def get_alternate_prediction() -> tuple[str, str]:
    """Получение предсказания с чередованием стратегий"""
    global last_prediction_type

    # Сортируем масти по частоте
    suits_sorted = sorted(rolling_suit_counts.items(), key=lambda x: x[1], reverse=True)

    if not suits_sorted:
        return '♣', "🎲 Нет данных"

    most_common_suit = suits_sorted[0][0]  # Самая частая
    second_common_suit = suits_sorted[1][0] if len(suits_sorted) > 1 else most_common_suit

    # Чередуем стратегии
    if PREDICTION_MODE == "alternate":
        if last_prediction_type == "most_common":
            last_prediction_type = "second_common"
            return second_common_suit, "🔄 Вторая по частоте"
        else:
            last_prediction_type = "most_common"
            return most_common_suit, "📈 Самая частая"

    elif PREDICTION_MODE == "most_common":
        return most_common_suit, "📈 Самая частая"

    elif PREDICTION_MODE == "rarest":
        rarest_suit = suits_sorted[-1][0]
        return rarest_suit, "⚖️ Редкая"

    return most_common_suit, "🎲 Случайно"


def should_make_prediction(game_num: int) -> bool:
    """Определяет, нужно ли делать предсказание для этой игры"""
    return game_num % 2 == 1  # Только нечётные игры


def create_prediction_dict(next_game_num: int) -> dict | None:
    """Создание словаря предсказания"""
    if len(game_history) < MIN_GAMES_FOR_PREDICTION:
        return None

    if not should_make_prediction(next_game_num):
        return None

    predicted_suit, strategy = get_alternate_prediction()

    prediction = {
        'game_num': next_game_num,
        'predicted_suit': predicted_suit,
        'strategy': strategy,
        'status': 'active',  # active, success, failed
        'prediction_time': datetime.now().isoformat(),
        'verification_game': None,
        'result': None,
        'statistics': rolling_suit_counts.copy(),
        'prediction_message_id': None  # ID сообщения в канале прогнозов
    }

    return prediction


async def send_prediction_to_channel(bot, prediction: dict):
    """Отправка предсказания в отдельный канал"""
    stats = prediction['statistics']
    suits_sorted = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    ranking = " → ".join([f"{suit}:{count}" for suit, count in suits_sorted])

    msg = (
        f"🔮 ПРЕДСКАЗАНИЕ #{prediction['game_num']}\n"
        f"Масть: {prediction['predicted_suit']}\n"
        f"Стратегия: {prediction['strategy']}\n"
        f"Статистика: ♣{stats['♣']} ♦{stats['♦']} ♥{stats['♥']} ♠{stats['♠']}\n"
        f"Рейтинг: {ranking}\n"
        f"Статус: ⏳ Ожидание..."
    )

    try:
        sent_message = await bot.send_message(chat_id=PREDICTION_CHANNEL_ID, text=msg)
        prediction['prediction_message_id'] = sent_message.message_id
        logger.info(f"✅ Отправлено предсказание #{prediction['game_num']}: {prediction['predicted_suit']}")
        return sent_message.message_id
    except Exception as e:
        logger.error(f"❌ Ошибка отправки предсказания: {e}")
        return None


async def update_prediction_status(bot, prediction: dict, result_game_num: int, result: str):
    """Обновление статуса предсказания в канале"""
    if not prediction.get('prediction_message_id'):
        return

    stats = prediction['statistics']
    suits_sorted = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    ranking = " → ".join([f"{suit}:{count}" for suit, count in suits_sorted])

    # Эмодзи для результата
    result_emoji = "✅" if result == "success" else "❌"
    status_text = "ПОПАДАНИЕ" if result == "success" else "ПРОМАХ"

    msg = (
        f"{result_emoji} ПРЕДСКАЗАНИЕ #{prediction['game_num']} - {status_text}\n"
        f"Масть: {prediction['predicted_suit']}\n"
        f"Стратегия: {prediction['strategy']}\n"
        f"Статистика на момент: ♣{stats['♣']} ♦{stats['♦']} ♥{stats['♥']} ♠{stats['♠']}\n"
        f"Рейтинг: {ranking}\n"
        f"Результат: Выпала в игре #{result_game_num}" if result == "success" else f"Результат: Не выпала за 3 игры"
    )

    try:
        await bot.edit_message_text(
            chat_id=PREDICTION_CHANNEL_ID,
            message_id=prediction['prediction_message_id'],
            text=msg
        )
        logger.info(f"📝 Обновлен статус предсказания #{prediction['game_num']}: {result}")
    except Exception as e:
        logger.error(f"❌ Ошибка обновления статуса предсказания: {e}")


async def verify_predictions(bot, current_game_data: dict):
    """Верификация активных предсказаний"""
    current_game_num = current_game_data['game_num']
    current_suits = current_game_data['player_suits'] + current_game_data['banker_suits']

    updated = False

    # Проверяем все активные предсказания
    for pred_num_str, prediction in list(predictions_history.items()):
        if prediction.get('status') != 'active':
            continue

        pred_num = int(pred_num_str)

        # Проверяем попадание (предсказание сработало)
        if prediction['predicted_suit'] in current_suits:
            prediction['status'] = 'success'
            prediction['verification_game'] = current_game_num
            prediction['result'] = 'hit'
            updated = True

            # Обновляем сообщение в канале
            await update_prediction_status(bot, prediction, current_game_num, "success")
            logger.info(
                f"🎯 ПОПАДАНИЕ: предсказание #{pred_num} → {prediction['predicted_suit']} (выпала в #{current_game_num})")

        # Проверяем промах (прошло 3 игры без попадания)
        elif current_game_num >= pred_num + 3:
            prediction['status'] = 'failed'
            prediction['verification_game'] = current_game_num
            prediction['result'] = 'miss'
            updated = True

            # Обновляем сообщение в канале
            await update_prediction_status(bot, prediction, current_game_num, "failed")
            logger.info(f"❌ ПРОМАХ: предсказание #{pred_num} → {prediction['predicted_suit']} (не выпала за 3 игры)")

    if updated:
        save_analytics_data()


# === 🛡️ ОСНОВНОЙ ОБРАБОТЧИК ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        message = update.channel_post
        is_edit = False
    elif update.edited_channel_post:
        message = update.edited_channel_post
        is_edit = True
    else:
        return

    if message.chat.id != SOURCE_CHAT_ID:
        return

    original_text = message.text or ""
    source_message_id = message.message_id
    
    # ===== НОВАЯ ПРОВЕРКА ПО ВРЕМЕНИ =====
    # Игнорируем сообщения старше 1 часа
    message_time = message.date.replace(tzinfo=None)
    one_hour_ago = datetime.now() - timedelta(hours=1)

    if message_time < one_hour_ago:
        logger.info(f"⏰ Пропускаю старое сообщение от {message_time}")
        return
    # ===== КОНЕЦ ПРОВЕРКИ =====

    # === ✅ ШАГ 1: ЗЕРКАЛИРОВАНИЕ ===
    enhanced_text = add_32_indicator(original_text)
    message_map = load_message_map()

    try:
        if is_edit:
            key = str(source_message_id)
            if key in message_map:
                target_msg_id = message_map[key]
                try:
                    await safe_edit_message(context.bot, TARGET_CHAT_ID, target_msg_id, enhanced_text)
                    logger.info(f"✏️ Отредактировано в зеркале: {target_msg_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка редактирования: {e}")
                    try:
                        sent = await safe_send_message(context.bot, TARGET_CHAT_ID, enhanced_text)
                        message_map[key] = sent.message_id
                        save_message_map(message_map)
                        logger.info(f"📤 Отправлено как новое: {sent.message_id}")
                    except Exception as e2:
                        logger.error(f"❌ Не удалось отправить: {e2}")
            else:
                sent = await safe_send_message(context.bot, TARGET_CHAT_ID, enhanced_text)
                message_map[key] = sent.message_id
                save_message_map(message_map)
                logger.info(f"📤 Отправлено как новое: {sent.message_id}")
        else:
            sent = await safe_send_message(context.bot, TARGET_CHAT_ID, enhanced_text)
            message_map[str(source_message_id)] = sent.message_id
            save_message_map(message_map)
            logger.info(f"📥 Зеркало: {sent.message_id} | {'🟩' if '🟩' in enhanced_text else '—'}")

    except Exception as e:
        logger.exception(f"❌ КРИТИЧЕСКАЯ ОШИБКА зеркалирования: {e}")

    # === 🔍 ШАГ 2: АНАЛИЗ И ПРЕДСКАЗАНИЯ ===
    try:
        game_data = parse_game_data(original_text, source_message_id)
        if not game_data:
            return

        # Обновляем статистику
        update_cycle_stats(game_data)
        update_rolling_stats(game_data)

        # Верифицируем предыдущие предсказания
        await verify_predictions(context.bot, game_data)

        # Создаем новое предсказание (только для нечетных игр)
        next_game_num = game_data['game_num'] + 1
        if should_make_prediction(next_game_num):
            prediction = create_prediction_dict(next_game_num)
            if prediction:
                # Сохраняем предсказание в историю
                predictions_history[str(next_game_num)] = prediction

                # Отправляем в канал прогнозов
                message_id = await send_prediction_to_channel(context.bot, prediction)
                if message_id:
                    prediction['prediction_message_id'] = message_id

                save_analytics_data()
                logger.info(f"🔮 Создано предсказание #{next_game_num}")

        logger.debug(f"🎲 Игра {game_data['game_num']} обработана")

    except Exception as e:
        logger.exception(f"⚠️ Ошибка анализа: {e}")


# === ▶️ ЗАПУСК ===
def main():
    load_analytics_data()
    logger.info(f"✅ Бот запущен")
    logger.info(f"📊 Зеркало: {TARGET_CHAT_ID}")
    logger.info(f"🔮 Канал прогнозов: {PREDICTION_CHANNEL_ID}")
    logger.info(f"📈 Статистика: {len(game_history)} игр, {len(predictions_history)} предсказаний")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(
        filters.Chat(SOURCE_CHAT_ID) & filters.TEXT,
        handle_message
    ))
    app.add_handler(MessageHandler(
        filters.Chat(SOURCE_CHAT_ID) & filters.UpdateType.EDITED_CHANNEL_POST & filters.TEXT,
        handle_message
    ))

    logger.info("⚡ Бот готов к работе")
    app.run_polling()


if __name__ == '__main__':
    main()