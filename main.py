import sys
import time
from datetime import datetime

print("=" * 50, flush=True)
print("✅ ТЕСТОВЫЙ СКРИПТ ЗАПУЩЕН", flush=True)
print(f"🕐 {datetime.now()}", flush=True)
print("=" * 50, flush=True)

while True:
    print(f"🔄 Бот работает... {datetime.now()}", flush=True)
    time.sleep(10)