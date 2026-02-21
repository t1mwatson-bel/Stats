import requests
import json
import time
from datetime import datetime
from collections import defaultdict
import urllib3

# Отключаем предупреждения о SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== НАСТРОЙКИ ==========
TOKEN = os.getenv("TOKEN", "8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU")
API_BASE = "https://1xlite-7636770.bar"
GAME_IDS = [697705521, 697704425]  # ID игр для отслеживания
# ================================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://1xlite-7636770.bar/',
}

# Маппинг рангов (константа)
RANK_MAP = {1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}

# ===== ЭТО И ЕСТЬ "ПАМЯТЬ" =====
# Словарь, который хранит маппинг мастей для каждой игры
# Ключ: ID игры, Значение: {код_масти: символ}
# Например: {697705521: {1: '♥️', 2: '♠️', 3: '♣️', 4: '♦️'}}
game_suit_mappings = {}

def get_game_details(game_id):
    """Получает детали игры из API 1x"""
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
            print(f"HTTP {response.status_code} для игры {game_id}")
            return None
    except Exception as e:
        print(f"Ошибка запроса для игры {game_id}: {e}")
        return None

def extract_cards_from_api(details):
    """Извлекает сырые данные карт игрока и банкира"""
    if not details or not details.get('Value'):
        return [], []

    sc = details['Value'].get('SC', {})
    player_cards = []
    banker_cards = []

    for item in sc.get('S', []):
        if isinstance(item, dict):
            key = item.get('Key')
            if key in ['P', 'B']:
                try:
                    cards = json.loads(item.get('Value', '[]'))
                    if key == 'P':
                        player_cards = cards
                    else:
                        banker_cards = cards
                except json.JSONDecodeError:
                    print(f"Ошибка парсинга JSON для {key}")
    return player_cards, banker_cards

# ===== ЗДЕСЬ ПРОИСХОДИТ ЗАПОМИНАНИЕ =====
def analyze_suit_mapping(player_cards, banker_cards, game_id):
    """
    СОЗДАЕТ И ЗАПОМИНАЕТ маппинг кодов мастей в символы.
    
    Важно: 
    - Если маппинг УЖЕ ЕСТЬ для этого game_id - просто возвращаем его
    - Если маппинга НЕТ - создаем и сохраняем навсегда
    - Больше НИКОГДА не меняем для этой игры
    """
    
    # ===== ПРОВЕРКА ПАМЯТИ =====
    # Смотрим, есть ли уже сохраненный маппинг для этой игры
    if game_id in game_suit_mappings:
        print(f"🔄 Использую сохраненный маппинг для игры {game_id}")
        return game_suit_mappings[game_id]

    print(f"🔍 Создаю новый маппинг для игры {game_id}...")
    
    all_cards = player_cards + banker_cards
    suit_stats = defaultdict(lambda: {'count': 0, 'rank_sum': 0, 'high_cards': 0})

    # Собираем статистику по кодам мастей
    for card in all_cards:
        if isinstance(card, dict):
            suit_code = card.get('S')
            rank = card.get('R')
            if suit_code and rank and suit_code != 0:
                suit_stats[suit_code]['count'] += 1
                suit_stats[suit_code]['rank_sum'] += rank
                if rank in [1, 11, 12, 13, 14]:  # Высокие карты
                    suit_stats[suit_code]['high_cards'] += 1

    # Если данных мало, создаем временный маппинг
    if len(suit_stats) < 4:
        mapping = {code: f'?{code}' for code in suit_stats.keys()}
    else:
        # Вычисляем средний ранг для каждой масти
        suit_avg_rank = {}
        for code, stats in suit_stats.items():
            suit_avg_rank[code] = stats['rank_sum'] / stats['count']

        # Сортируем по среднему рангу
        sorted_suits = sorted(suit_avg_rank.items(), key=lambda x: x[1], reverse=True)
        
        # Традиционный порядок мастей
        suit_symbols = ['♥️', '♠️', '♣️', '♦️']

        mapping = {}
        for i, (suit_code, _) in enumerate(sorted_suits):
            if i < len(suit_symbols):
                mapping[suit_code] = suit_symbols[i]
            else:
                mapping[suit_code] = f'?{suit_code}'

    # ===== СОХРАНЕНИЕ В ПАМЯТЬ =====
    # Записываем созданный маппинг в глобальный словарь
    # Теперь он будет использоваться ВСЕГДА для этой игры
    game_suit_mappings[game_id] = mapping
    print(f"✅ Маппинг сохранен для игры {game_id}: {mapping}")
    
    return mapping

def parse_card(card_dict, game_id):
    """Преобразует карту в строку, используя сохраненный маппинг"""
    if not isinstance(card_dict, dict):
        return '??'

    rank_num = card_dict.get('R')
    suit_code = card_dict.get('S', 0)

    # Определяем ранг
    if rank_num in RANK_MAP:
        rank = RANK_MAP[rank_num]
    elif rank_num and 2 <= rank_num <= 10:
        rank = str(rank_num)
    else:
        rank = '?'

    # Определяем масть
    if suit_code == 0:
        suit = '?'  # Закрытая карта
    else:
        # ===== ИСПОЛЬЗОВАНИЕ ПАМЯТИ =====
        # Берем маппинг из сохраненного словаря
        mapping = game_suit_mappings.get(game_id, {})
        suit = mapping.get(suit_code, f'?{suit_code}')

    return f"{rank}{suit}"

def calculate_score(cards):
    """Вычисляет сумму очков в баккаре"""
    total = 0
    for card in cards:
        if isinstance(card, dict):
            rank = card.get('R', 0)
            if rank in [1, 14]:  # Туз = 1
                total += 1
            elif rank in [11, 12, 13]:  # Валет, Дама, Король = 0
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
    """Получает и анализирует данные игры"""
    details = get_game_details(game_id)
    if not details:
        return None

    # Извлекаем карты
    player_cards, banker_cards = extract_cards_from_api(details)

    # ===== ВЫЗОВ ФУНКЦИИ С ПАМЯТЬЮ =====
    # Если маппинга еще нет - создаст и запомнит
    # Если уже есть - просто вернет сохраненный
    analyze_suit_mapping(player_cards, banker_cards, game_id)

    # Вычисляем очки
    player_score = calculate_score(player_cards)
    banker_score = calculate_score(banker_cards)
    winner = determine_winner(player_score, banker_score)

    # Преобразуем карты
    player_cards_str = [parse_card(c, game_id) for c in player_cards]
    banker_cards_str = [parse_card(c, game_id) for c in banker_cards]

    return {
        'game_number': game_number,
        'game_id': game_id,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'player_cards': player_cards_str,
        'banker_cards': banker_cards_str,
        'player_score': player_score,
        'banker_score': banker_score,
        'winner': winner,
        'suit_mapping': game_suit_mappings.get(game_id, {})
    }

def display_game(game_data):
    """Выводит данные игры"""
    if not game_data:
        return

    p_cards = ' '.join(game_data['player_cards']) if game_data['player_cards'] else '?'
    b_cards = ' '.join(game_data['banker_cards']) if game_data['banker_cards'] else '?'

    if game_data['winner'] == 'Player':
        winner_emoji = '👤'
    elif game_data['winner'] == 'Banker':
        winner_emoji = '🏦'
    else:
        winner_emoji = '🤝'

    print(f"\n[{game_data['timestamp']}] Игра #{game_data['game_number']} (ID: {game_data['game_id']})")
    print(f"👤 Player: {p_cards} = {game_data['player_score']}")
    print(f"🏦 Banker: {b_cards} = {game_data['banker_score']}")
    print(f"🏆 Победитель: {winner_emoji} {game_data['winner']}")

    if game_data['suit_mapping']:
        mapping_str = ', '.join([f"{k}:{v}" for k, v in game_data['suit_mapping'].items()])
        print(f"🔍 Маппинг: {mapping_str}")

def main():
    print("🚀 МОНИТОРИНГ С ЗАПОМИНАНИЕМ МАСТЕЙ")
    print("=" * 70)

    iteration = 0
    last_game_states = {game_id: '' for game_id in GAME_IDS}

    try:
        while True:
            iteration += 1
            print(f"\n--- Цикл #{iteration} ---")

            for game_id in GAME_IDS:
                game_data = get_game_data(game_id, iteration)

                if game_data:
                    state_key = f"{game_data['player_cards']}_{game_data['banker_cards']}"
                    if last_game_states[game_id] != state_key:
                        display_game(game_data)
                        last_game_states[game_id] = state_key
                else:
                    print(f"❌ Игра {game_id}: нет данных")

            print("\n⏳ Ожидание 5 секунд...")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n📊 ИТОГОВАЯ ПАМЯТЬ МАСТЕЙ:")
        for game_id, mapping in game_suit_mappings.items():
            print(f"Игра {game_id}: {mapping}")
        print("\n👋 Завершение.")

if __name__ == "__main__":
    main()