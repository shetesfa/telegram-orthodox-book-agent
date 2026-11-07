import asyncio
import sys
from app.telegram.client import telegram_manager
from app.telegram.harvester import REJECT_KEYWORDS

sys.stdout.reconfigure(encoding="utf-8")

async def inspect():
    await telegram_manager.init_client()
    client = telegram_manager.client
    dest_entity = await client.get_entity("https://t.me/+2EsS9AQ1kt9mYmFk")
    async for msg in client.iter_messages(dest_entity, limit=5):
        fn = ""
        if msg.document:
            for attr in msg.document.attributes:
                if hasattr(attr, "file_name"):
                    fn = attr.file_name
                    break
        text = f"{fn} {msg.text or ''}".lower()
        print(f"Msg {msg.id}: {fn}")
        matched = [b for b in REJECT_KEYWORDS if b in text]
        if matched:
            print(f"  -> Matches: {matched}")

if __name__ == "__main__":
    asyncio.run(inspect())
