import os
import asyncio
import random
from telegram import Bot
from datetime import datetime

# ТВОИ ДАННЫЕ
TOKEN = "8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU"
CHANNEL_ID = -1003179573402
game_counter = 1248

bot = Bot(token=TOKEN)
print("✅ Bot запущен!")

suits = ['♥️', '♠️', '♣️', '♦️']
ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

async def send_game():
    global game_counter
    
    # Player (3 карты)
    player_cards = [random.choice(ranks) + random.choice(suits) for _ in range(3)]
    player_score = random.randint(0, 9)
    
    # Banker (3 карты)  
    banker_cards = [random.choice(ranks) + random.choice(suits) for _ in range(3)]
    banker_score = random.randint(0, 9)
    
    message = f"""#N{game_counter} {player_score} ({' '.join(player_cards)}) - ✅{banker_score} ({' '.join(banker_cards)})
#П2 #T2 #C3_3"""
    
    await bot.send_message(CHANNEL_ID, message)
    print(f"✅ #N{game_counter} отправлено!")
    game_counter += 1

async def main():
    print(f"🚀 СТАРТ #N{game_counter}")
    
    while True:
        await send_game()
        await asyncio.sleep(12)  # 12 сек между играми

if __name__ == "__main__":
    asyncio.run(main())
