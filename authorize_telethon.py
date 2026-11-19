import asyncio
import os
from telethon import TelegramClient

API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')

SESSION = 'favt_session'

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)

    await client.start()

    print('Telethon успешно авторизован!')

    await client.disconnect()

asyncio.run(main())
