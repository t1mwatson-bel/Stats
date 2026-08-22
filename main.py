import requests
import json
import time
from datetime import datetime, timedelta
import pytz
import sys
import os

# =====================================================================
# ПРИНУДИТЕЛЬНЫЙ ВЫВОД ЛОГОВ
# =====================================================================

sys.stdout.flush()

print("=" * 70, flush=True)
print("🃏 ПАРСЕР БАККАРА", flush=True)
print("=" * 70, flush=True)


# =====================================================================
# НАСТРОЙКИ TELEGRAM
# =====================================================================
# Никаких токенов и ID в исходнике.
# Они должны быть заданы на хостинге:
#
# BOT_TOKEN=...
# CHAT_ID=...
# =====================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN:
    raise RuntimeError("❌ Переменная окружения BOT_TOKEN не задана")

if not CHAT_ID:
    raise RuntimeError("❌ Переменная окружения CHAT_ID не задана")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# =====================================================================
# ВРЕМЕННАЯ ЗОНА
# =====================================================================

MOSCOW_TZ = pytz.timezone("Europe/Moscow")


# =====================================================================
# СОСТОЯНИЕ
# =====================================================================

messages = {}
processed_games = set()


# =====================================================================
# КАРТЫ
# =====================================================================

SUITS = {
    0: "♠️",
    1: "♣️",
    2: "♦️",
    3: "♥️"
}

RANKS = {
    1: "A",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7",
    8: "8",
    9: "9",
    10: "10",
    11: "J",
    12: "Q",
    13: "K"
}


# =====================================================================
# MELBET
# =====================================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://melbet-38497.pro/ru/live/baccarat/",
}


# =====================================================================
# URL
# =====================================================================
#
# Здесь оставлены твои старые URL.
#
# ВАЖНО:
# если именно здесь проблема с выбором игр, по логам ниже будет видно,
# что реально возвращает API.
# =====================================================================

LIST_URL = (
    "https://melbet-38497.pro/service-api/LiveFeed/"
    "Get1x2_VZip"
    "?sports=236"
    "&champs=2050671"
    "&count=40"
    "&gr=1521"
    "&mode=4"
    "&country=192"
    "&partner=8"
    "&getEmpty=true"
    "&virtualSports=true"
    "&noFilterBlockEvent=true"
)

DETAIL_URL = (
    "https://melbet-38497.pro/service-api/LiveFeed/"
    "GetGameZip"
    "?id={game_id}"
    "&isSubGames=true"
    "&GroupEvents=true"
    "&countevents=250"
    "&grMode=4"
    "&partner=8"
    "&topGroups="
    "&country=192"
    "&marketType=1"
    "&isNewBuilder=true"
)


print("✅ Конфигурация загружена", flush=True)
print(
    f"📡 Telegram CHAT_ID: {CHAT_ID}",
    flush=True
)
print("=" * 70, flush=True)


# =====================================================================
# НОМЕР ИГРЫ
# =====================================================================

def get_game_number():
    """
    Текущий номер игры относительно 03:00 по Москве.

    Это твоя старая логика нумерации.
    """

    now = datetime.now(MOSCOW_TZ)

    start = now.replace(
        hour=3,
        minute=0,
        second=0,
        microsecond=0
    )

    if now < start:
        start -= timedelta(days=1)

    diff_minutes = (now - start).total_seconds() / 60

    return int(diff_minutes) % 1440 + 1


# =====================================================================
# ПОЛУЧЕНИЕ СПИСКА ИГР
# =====================================================================

def get_active_games():

    try:

        print("🔎 Запрашиваю список игр...", flush=True)

        resp = requests.get(
            LIST_URL,
            headers=HEADERS,
            timeout=15
        )

        print(
            f"📡 LIST HTTP: {resp.status_code}",
            flush=True
        )

        if resp.status_code != 200:

            print(
                f"❌ LIST ошибка: {resp.text[:1000]}",
                flush=True
            )

            return []

        try:
            data = resp.json()

        except Exception as e:

            print(
                f"❌ LIST не JSON: {e}",
                flush=True
            )

            print(
                resp.text[:3000],
                flush=True
            )

            return []

        if not isinstance(data, dict):

            print(
                f"❌ LIST имеет неожиданный тип: {type(data)}",
                flush=True
            )

            return []

        games = data.get("Value", [])

        if not isinstance(games, list):

            print(
                f"❌ Value имеет тип {type(games)}",
                flush=True
            )

            print(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )[:5000],
                flush=True
            )

            return []

        print(
            f"📋 API вернул игр: {len(games)}",
            flush=True
        )

        # -------------------------------------------------------------
        # Показываем найденные игры
        # -------------------------------------------------------------

        for index, game in enumerate(games, start=1):

            gid = game.get("I")

            print(
                f"   [{index}] "
                f"ID={gid} "
                f"N={game.get('N')} "
                f"E={game.get('E')}",
                flush=True
            )

        active = []

        for game in games:

            gid = game.get("I")

            if not gid:
                continue

            gid = str(gid)

            if gid in processed_games:
                continue

            active.append(game)

        print(
            f"🎯 Новых/активных игр: {len(active)}",
            flush=True
        )

        return active

    except requests.RequestException as e:

        print(
            f"❌ Ошибка запроса списка игр: {e}",
            flush=True
        )

        return []

    except Exception as e:

        print(
            f"❌ Ошибка get_active_games(): {e}",
            flush=True
        )

        return []


# =====================================================================
# ПОЛУЧЕНИЕ ДАННЫХ КОНКРЕТНОЙ ИГРЫ
# =====================================================================

def get_game_data(game_id):

    try:

        url = DETAIL_URL.format(
            game_id=game_id
        )

        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=10
        )

        print(
            f"🎮 GAME {game_id}: HTTP {resp.status_code}",
            flush=True
        )

        if resp.status_code != 200:

            print(
                f"❌ GAME {game_id}: "
                f"{resp.text[:1000]}",
                flush=True
            )

            return None

        try:

            data = resp.json()

        except Exception as e:

            print(
                f"❌ GAME {game_id}: ответ не JSON: {e}",
                flush=True
            )

            print(
                resp.text[:5000],
                flush=True
            )

            return None

        return data

    except requests.RequestException as e:

        print(
            f"❌ GAME {game_id}: ошибка HTTP: {e}",
            flush=True
        )

        return None

    except Exception as e:

        print(
            f"❌ GAME {game_id}: {e}",
            flush=True
        )

        return None


# =====================================================================
# ИЗВЛЕЧЕНИЕ КАРТ
# =====================================================================

def parse_cards(value):

    if value is None:
        return []

    # Иногда API может уже вернуть список
    if isinstance(value, list):
        return value

    if not isinstance(value, str):
        return []

    try:
        result = json.loads(value)

        if isinstance(result, list):
            return result

    except Exception:
        pass

    return []


# =====================================================================
# ФОРМАТИРОВАНИЕ КАРТ
# =====================================================================

def format_cards(cards):

    if not cards:
        return ""

    output = []

    for card in cards:

        if not isinstance(card, dict):
            return None

        cs = card.get("CS", 0)
        cv = card.get("CV", 0)

        if not cs or not cv:
            return None

        suit = SUITS.get(
            cs,
            "?"
        )

        rank = RANKS.get(
            cv,
            str(cv)
        )

        output.append(
            f"{rank}{suit}"
        )

    return "".join(output)


# =====================================================================
# ПОДСЧЁТ ОЧКОВ
# =====================================================================

def calculate_score(cards):

    if not cards:
        return 0

    score = 0

    for card in cards:

        if not isinstance(card, dict):
            return -1

        cv = card.get("CV", 0)

        if cv == 0:
            return -1

        if cv == 1:
            score += 1

        elif 2 <= cv <= 9:
            score += cv

        # 10/J/Q/K = 0
        elif 10 <= cv <= 13:
            score += 0

    return score % 10


# =====================================================================
# ПРОВЕРКА КОРРЕКТНОСТИ КАРТ
# =====================================================================

def cards_are_valid(cards):

    if not cards:
        return False

    for card in cards:

        if not isinstance(card, dict):
            return False

        cv = card.get("CV", 0)
        cs = card.get("CS", 0)

        if not cv or not cs:
            return False

    return True


# =====================================================================
# СОСТОЯНИЕ ИГРЫ
# =====================================================================

def is_finished_by_state(state):

    if not state:
        return False

    state = str(state).lower().strip()

    finished_states = {
        "игра завершена",
        "завершена",
        "завершено",
        "finished",
        "finish",
        "ended",
        "closed"
    }

    return state in finished_states


# =====================================================================
# ТИП ИГРЫ
# =====================================================================

def is_early_win(p_score, d_score):

    return (
        p_score in [8, 9]
        or
        d_score in [8, 9]
    )


def get_game_type(
    p_score,
    d_score
):

    if p_score == d_score:
        return "X"

    if is_early_win(
        p_score,
        d_score
    ):
        return "R"

    return "N"


# =====================================================================
# ПОБЕДИТЕЛЬ
# =====================================================================

def get_result_symbol(
    p_score,
    d_score
):

    if p_score > d_score:
        return "✅"

    if d_score > p_score:
        return "❌"

    return "🔰"


# =====================================================================
# ФОРМИРОВАНИЕ СООБЩЕНИЯ
# =====================================================================

def build_message(
    game_num,
    player_cards,
    dealer_cards,
    p_score,
    d_score,
    state
):

    p_hand = format_cards(
        player_cards
    )

    d_hand = format_cards(
        dealer_cards
    )

    if p_hand is None:
        return None

    if dealer_cards and d_hand is None:
        return None

    total = p_score + d_score

    gtype = get_game_type(
        p_score,
        d_score
    )

    # -------------------------------------------------------------
    # Финальная игра
    # -------------------------------------------------------------

    if is_finished_by_state(state):

        result = get_result_symbol(
            p_score,
            d_score
        )

        return (
            f"#{gtype}{game_num}. "
            f"{p_score}({p_hand}) - "
            f"{result}"
            f"{d_score}({d_hand}) "
            f"#T{total}"
        )

    # -------------------------------------------------------------
    # Игра ещё идёт
    # -------------------------------------------------------------

    if dealer_cards:

        arrow = "▶️"

    else:

        arrow = "◀️"

    return (
        f"#{gtype}{game_num}. "
        f"{p_score}({p_hand}) "
        f"{arrow} "
        f"{d_score}({d_hand}) "
        f"#T{total}"
    )


# =====================================================================
# TELEGRAM: ОТПРАВКА
# =====================================================================

def send_message(text):

    try:

        response = requests.post(
            API + "/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": text
            },
            timeout=10
        )

        if response.status_code == 200:

            result = response.json()

            if result.get("ok"):

                return result["result"]["message_id"]

        print(
            f"❌ Telegram sendMessage: "
            f"{response.status_code} "
            f"{response.text[:1000]}",
            flush=True
        )

    except Exception as e:

        print(
            f"❌ Telegram sendMessage: {e}",
            flush=True
        )

    return None


# =====================================================================
# TELEGRAM: РЕДАКТИРОВАНИЕ
# =====================================================================

def edit_message(
    msg_id,
    text
):

    try:

        url = (
            f"{API}/editMessageText"
        )

        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "message_id": msg_id,
                "text": text
            },
            timeout=10
        )

        if response.status_code == 200:

            result = response.json()

            if result.get("ok"):
                return True

        # Telegram иногда возвращает ошибку, если текст
        # фактически не изменился.
        print(
            f"⚠️ Telegram editMessageText: "
            f"{response.status_code} "
            f"{response.text[:500]}",
            flush=True
        )

    except Exception as e:

        print(
            f"❌ Telegram editMessageText: {e}",
            flush=True
        )

    return False


# =====================================================================
# TELEGRAM: ПРОВЕРКА
# =====================================================================

def test_telegram():

    try:

        response = requests.get(
            API + "/getMe",
            timeout=10
        )

        if response.status_code != 200:

            print(
                "❌ Telegram getMe ошибка:",
                response.text[:1000],
                flush=True
            )

            return False

        data = response.json()

        if not data.get("ok"):

            print(
                "❌ Telegram токен не работает:",
                data,
                flush=True
            )

            return False

        bot = data.get(
            "result",
            {}
        )

        print(
            f"🤖 Telegram bot: "
            f"@{bot.get('username')}",
            flush=True
        )

        return True

    except Exception as e:

        print(
            f"❌ Telegram test: {e}",
            flush=True
        )

        return False


# =====================================================================
# ОБРАБОТКА ОДНОЙ ИГРЫ
# =====================================================================

def process_game(game):

    gid = str(
        game.get("I")
    )

    if not gid:
        return

    if gid in processed_games:
        return

    print(
        "-" * 60,
        flush=True
    )

    print(
        f"🎮 Обработка игры ID={gid}",
        flush=True
    )

    data = get_game_data(
        gid
    )

    if not data:

        print(
            f"⏭️ {gid}: нет данных",
            flush=True
        )

        return

    if not isinstance(data, dict):

        print(
            f"⏭️ {gid}: неожиданный формат",
            flush=True
        )

        return

    value = data.get(
        "Value",
        {}
    )

    if not isinstance(value, dict):

        print(
            f"⏭️ {gid}: Value не dict",
            flush=True
        )

        return

    sc = value.get(
        "SC",
        {}
    )

    if not isinstance(sc, dict):

        print(
            f"⏭️ {gid}: SC не dict",
            flush=True
        )

        return

    state = sc.get(
        "CPS",
        ""
    )

    print(
        f"📌 {gid}: state={state}",
        flush=True
    )

    player_cards = []
    dealer_cards = []

    sections = sc.get(
        "S",
        []
    )

    if not isinstance(
        sections,
        list
    ):

        print(
            f"⏭️ {gid}: S не list",
            flush=True
        )

        return

    # -------------------------------------------------------------
    # Извлекаем P и B
    # -------------------------------------------------------------

    for item in sections:

        if not isinstance(
            item,
            dict
        ):
            continue

        key = item.get(
            "Key"
        )

        if key == "P":

            player_cards = parse_cards(
                item.get("Value")
            )

        elif key == "B":

            dealer_cards = parse_cards(
                item.get("Value")
            )

    print(
        f"🃏 {gid}: "
        f"P={len(player_cards)} "
        f"B={len(dealer_cards)}",
        flush=True
    )

    # -------------------------------------------------------------
    # Игрок должен иметь карты
    # -------------------------------------------------------------

    if not cards_are_valid(
        player_cards
    ):

        print(
            f"⏭️ {gid}: карты игрока ещё не готовы",
            flush=True
        )

        return

    # -------------------------------------------------------------
    # Если дилерские карты есть, проверяем их
    # -------------------------------------------------------------

    if dealer_cards:

        if not cards_are_valid(
            dealer_cards
        ):

            print(
                f"⏭️ {gid}: карты дилера ещё не готовы",
                flush=True
            )

            return

    # -------------------------------------------------------------
    # Считаем
    # -------------------------------------------------------------

    p_score = calculate_score(
        player_cards
    )

    d_score = calculate_score(
        dealer_cards
    )

    if p_score < 0:

        print(
            f"⏭️ {gid}: "
            f"не удалось посчитать P",
            flush=True
        )

        return

    if d_score < 0:

        print(
            f"⏭️ {gid}: "
            f"не удалось посчитать B",
            flush=True
        )

        return

    print(
        f"📊 {gid}: "
        f"P={p_score}, "
        f"B={d_score}",
        flush=True
    )

    # -------------------------------------------------------------
    # Номер игры
    # -------------------------------------------------------------

    game_num = get_game_number()

    # -------------------------------------------------------------
    # Формируем сообщение
    # -------------------------------------------------------------

    message = build_message(
        game_num,
        player_cards,
        dealer_cards,
        p_score,
        d_score,
        state
    )

    if not message:

        print(
            f"⏭️ {gid}: "
            f"не удалось сформировать сообщение",
            flush=True
        )

        return

    # -------------------------------------------------------------
    # Уже существует сообщение
    # -------------------------------------------------------------

    if gid in messages:

        success = edit_message(
            messages[gid],
            message
        )

        if success:

            print(
                f"🔄 Обновлена {gid}: "
                f"{message}",
                flush=True
            )

    # -------------------------------------------------------------
    # Новое сообщение
    # -------------------------------------------------------------

    else:

        message_id = send_message(
            message
        )

        if message_id:

            messages[gid] = message_id

            print(
                f"📤 Новая {gid}: "
                f"{message}",
                flush=True
            )

        else:

            print(
                f"❌ Не удалось отправить "
                f"{gid}",
                flush=True
            )

            return

    # -------------------------------------------------------------
    # Завершаем только по состоянию API
    # -------------------------------------------------------------

    if is_finished_by_state(
        state
    ):

        processed_games.add(
            gid
        )

        print(
            f"🏁 Завершена {gid}",
            flush=True
        )


# =====================================================================
# ОСНОВНОЙ ЦИКЛ
# =====================================================================

def main():

    print(
        "🚀 ПАРСЕР БАККАРА ЗАПУЩЕН",
        flush=True
    )

    print(
        "=" * 70,
        flush=True
    )

    # -------------------------------------------------------------
    # Проверяем Telegram
    # -------------------------------------------------------------

    if not test_telegram():

        print(
            "❌ Telegram недоступен. "
            "Проверь BOT_TOKEN.",
            flush=True
        )

        return

    # -------------------------------------------------------------
    # Главный цикл
    # -------------------------------------------------------------

    while True:

        try:

            games = get_active_games()

            if not games:

                print(
                    "💤 Игры не найдены. "
                    "Повтор через 3 сек.",
                    flush=True
                )

                time.sleep(3)

                continue

            # -----------------------------------------------------
            # Обрабатываем найденные игры
            # -----------------------------------------------------

            for game in games:

                try:

                    process_game(
                        game
                    )

                except Exception as e:

                    print(
                        f"❌ Ошибка обработки игры: {e}",
                        flush=True
                    )

                time.sleep(
                    0.3
                )

            # -----------------------------------------------------
            # Ограничиваем память
            # -----------------------------------------------------

            if len(processed_games) > 500:

                print(
                    "🧹 Очищаю processed_games",
                    flush=True
                )

                processed_games.clear()

            time.sleep(
                1
            )

        except KeyboardInterrupt:

            print(
                "🛑 Остановка...",
                flush=True
            )

            break

        except Exception as e:

            print(
                f"❌ Ошибка главного цикла: {e}",
                flush=True
            )

            time.sleep(
                5
            )


# =====================================================================
# START
# =====================================================================

if __name__ == "__main__":

    main()