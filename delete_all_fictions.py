import asyncio
import sys
import re

sys.stdout.reconfigure(encoding="utf-8")

from app.telegram.client import telegram_manager
from app.database import get_settings

TARGET_CHANNEL_LINK = "https://t.me/+2EsS9AQ1kt9mYmFk"

# በትክክል ልብወለድ፣ ሳይኮሎጂ፣ ፖለቲካ እና ዓለማዊ መጻሕፍት ጠቋሚዎች
UNWANTED_PATTERNS = [
    "goodamharicbooks", "kooblife", "እፍታ", "ደስፔንዛ", "አእምሮህ", "ገብረ-ክርስቶሰ ደስታ",
    "የሰርቆ_አደሮች", "ትኩሳት", "ቆርጠሀት", "ያገር ልጅ", "በራስ መተማመን", "የተናቁ ዕንቁዎች",
    "ጠያይም መላእክት", "እኮ እንዴት", "የነጋሶ መንገድ", "ዳንኤል ተረፈ", "ሳይላክ የቀረ",
    "ህልፈተ አንጃ", "ኢህአፓ", "መንገድ ስጡኝ", "የከፍተኛ ትምህርት", "ጳውሎስ ኞኞ",
    "ሀሁ በስድስት ወር", "ጸጋዬ ገብረ", "የጉድጓዱ ምስጢር", "ገዳሙ ገዛኸኝ", "ደገልሃን",
    "ጌታቸው ጳውሎስ", "አዜብ", "መስፍን ሀብተማርያም", "የደም ዕንባ", "ዳዊት ወልደጊዮርጊስ",
    "ኤርሚያስ አመልጋ", "ስሞተኛው", "ይኩኖ", "ቴዎድሮስ እስከ ቀዳማዊ", "ተክለጻድቅ መኩርያ",
    "ልብወለድ", "ልቦለድ", "fiction", "novel", "ዳንኤል ክብረት"
]

def is_unwanted(text: str) -> bool:
    t = text.lower()
    for p in UNWANTED_PATTERNS:
        if p in t:
            return True
    return False

async def main():
    await telegram_manager.init_client()
    client = telegram_manager.client
    if not client or not client.is_connected() or not await client.is_user_authorized():
        print("Telegram client not authorized!")
        return

    dest_entity = await client.get_entity(TARGET_CHANNEL_LINK)
    print(f"Connected to: {getattr(dest_entity, 'title', '')}")

    to_delete = []
    names = []

    print("Scanning last 200 messages in channel...")
    async for msg in client.iter_messages(dest_entity, limit=200):
        fn = ""
        if msg.document:
            for attr in msg.document.attributes:
                if hasattr(attr, "file_name"):
                    fn = attr.file_name
                    break
        combined = f"{fn} {msg.text or ''}".lower()
        if is_unwanted(combined):
            to_delete.append(msg.id)
            names.append(fn or f"Msg {msg.id}")
            print(f"❌ To delete: {fn}")

    if to_delete:
        print(f"\nDeleting {len(to_delete)} messages from channel...")
        await client.delete_messages(dest_entity, to_delete)
        print(f"✅ Successfully deleted {len(to_delete)} unwanted books from the channel!")
    else:
        print("No unwanted messages found.")

if __name__ == "__main__":
    asyncio.run(main())
