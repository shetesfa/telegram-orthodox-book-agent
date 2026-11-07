import asyncio
import sys
import re

sys.stdout.reconfigure(encoding="utf-8")

from app.telegram.client import telegram_manager
from app.database import get_settings

TARGET_CHANNEL_LINK = "https://t.me/+2EsS9AQ1kt9mYmFk"

# በትክክል ልብወለድ፣ ፖለቲካ እና መንፈሳዊ ያልሆኑ ቃላትና ስሞች
FICTION_AND_SECULAR_MARKERS = [
    "kooblife", "ትኩሳት", "ቆርጠሀት", "ያገር ልጅ", "በራስ መተማመን", "የተናቁ ዕንቁዎች",
    "ጠያይም መላእክት", "እኮ እንዴት", "የነጋሶ መንገድ", "ዳንኤል ተረፈ", "ሳይላክ የቀረ",
    "ህልፈተ አንጃ", "ኢህአፓ", "መንገድ ስጡኝ", "የከፍተኛ ትምህርት", "ጳውሎስ ኞኞ",
    "ሀሁ በስድስት ወር", "ጸጋዬ ገብረ", "የጉድጓዱ ምስጢር", "ገዳሙ ገዛኸኝ", "ደገልሃን",
    "ጌታቸው ጳውሎስ", "አዜብ", "መስፍን ሀብተማርያም", "የደም ዕንባ", "ዳዊት ወልደጊዮርጊስ",
    "ኤርሚያስ አመልጋ", "ስሞተኛው", "ይኩኖ", "ቴዎድሮስ እስከ ቀዳማዊ", "ተክለጻድቅ መኩርያ",
    "ልብወለድ", "ልቦለድ", "fiction", "novel", "ፍቅር", "ግጥም", "ፖለቲካ"
]

def is_fiction_or_secular(text: str) -> bool:
    t = text.lower()
    for m in FICTION_AND_SECULAR_MARKERS:
        if m in t:
            # ፍቅረ እግዚአብሔር፣ ፍቅረ መስቀል እንዳይሰረዙ
            if m == "ፍቅር" and any(k in t for k in ["ፍቅረ እግዚአብሔር", "ፍቅረ መስቀል", "ፍቅረ ቅዱሳን"]):
                continue
            return True
    return False

async def main():
    await telegram_manager.connect()
    client = telegram_manager.client
    if not client or not client.is_connected() or not await client.is_user_authorized():
        print("Telegram client not authorized!")
        return

    dest_entity = await client.get_entity(TARGET_CHANNEL_LINK)
    print(f"Connected to channel: {getattr(dest_entity, 'title', '')}")

    to_delete_ids = []
    deleted_titles = []

    print("Scanning messages in channel...")
    async for msg in client.iter_messages(dest_entity, limit=100):
        text = msg.text or ""
        fn = ""
        if msg.document:
            for attr in msg.document.attributes:
                if hasattr(attr, "file_name"):
                    fn = attr.file_name
                    break

        combined = f"{fn} {text}"
        if is_fiction_or_secular(combined):
            to_delete_ids.append(msg.id)
            deleted_titles.append(fn or text[:40])
            print(f"❌ FOUND FICTION/SECULAR [Msg ID {msg.id}]: {fn}")

    if to_delete_ids:
        print(f"\nDeleting {len(to_delete_ids)} fiction/secular messages from channel...")
        # ቴሌግራም መልእክቶችን በባች ለመሰረዝ ይፈቅዳል
        await client.delete_messages(dest_entity, to_delete_ids)
        print(f"✅ Successfully deleted {len(to_delete_ids)} messages from the channel!")
        print("\nDeleted list:")
        for t in deleted_titles:
            print(f" - {t}")
    else:
        print("No fiction messages found in the recent history.")

if __name__ == "__main__":
    asyncio.run(main())
