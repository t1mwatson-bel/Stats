import os
import asyncio
from telegram import Bot

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003179573402"))

print(f"🔍 TOKEN: {TOKEN[:20]}...")
print(f"🔍 CHANNEL_ID: {CHANNEL_ID}")

bot = Bot(token=TOKEN)

async def test_message():
    try:
        await bot.send_message(CHANNEL_ID, "#N1248 ТЕСТ ✅ Бот работает!")
        print("✅ ТЕСТОВОЕ СООБЩЕНИЕ ОТПРАВЛЕНО В КАНАЛ!")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

async def main():
    print("🚀 Тестируем Telegram...")
    await test_message()
    print("✅ Тест завершён. Проверяй канал!")

if __name__ == "__main__":
    asyncio.run(main())
