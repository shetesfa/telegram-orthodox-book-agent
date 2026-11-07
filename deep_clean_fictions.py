import asyncio
import sys
import re

sys.stdout.reconfigure(encoding="utf-8")

from app.telegram.client import telegram_manager

TARGET_CHANNEL_LINK = "https://t.me/+2EsS9AQ1kt9mYmFk"

# የኦርቶዶክስ ተዋሕዶ መንፈሳዊ ቁልፍ ቃላት
ORTHODOX_SPIRITUAL_WORDS = [
    "ገድል", "ድርሳን", "አንድምታ", "ትርጓሜ", "ቅዳሴ", "ውዳሴ", "ሰዓታት", "ድጓ", 
    "ጾመ ድጓ", "ዝማሬ", "መዋሥዕት", "ነገረ ማርያም", "ሃይማኖተ አበው", "ፍትሐ ነገሥት",
    "ስንክሳር", "ማኅበረ ቅዱሳን", "ዝክረ ቅዱሳን", "ምስጢረ", "ዜና ቅዱሳን", "አቡነ", 
    "መነኮሳት", "አረጋዊ መንፈሳዊ", "ማር ይስሐቅ", "ፊልክስዩስ", "ባሕረ ሐሳብ", "ሥርዓተ",
    "መጽሐፍ ቅዱስ", "መፅሐፍ ቅዱስ", "ወንጌል", "ጳውሎስ መልእክት", "ኦሪት", "መዝሙረ ዳዊት",
    "መልክአ", "መልክዐ", "አርጋኖን", "ሰይፈ ሥላሴ", "ተአምረ ማርያም", "ተአምረ ኢየሱስ",
    "ቅዱስ ያሬድ", "ማኅሌት", "ዜማ"
]

# በግልጽ የማይፈቀዱ (ፖለቲካ፣ ታሪክ፣ ልብወለድ፣ ዓለማዊ)
EXPLICIT_REJECT = [
    "ትግላችን", "መንግስቱ ኃይለ", "የቡርቃ_ዝምታ", "ተስፋዬ ገብረአብ", "ማፊያ", "ወዳጄነህ",
    "ዳግማዊ ምኒልክ", "ምኒልክ", "አባ ገብርሃና", "ገብርሃና", "ትኩሳት", "ቆርጠሀት", 
    "ያገር ልጅ", "በራስ መተማመን", "የተናቁ ዕንቁዎች", "ጠያይም መላእክት", "እኮ እንዴት", 
    "የነጋሶ መንገድ", "ዳንኤል ተረፈ", "ሳይላክ የቀረ", "ህልፈተ አንጃ", "ኢህአፓ", "መንገድ ስጡኝ", 
    "የከፍተኛ ትምህርት", "ጳውሎስ ኞኞ", "ሀሁ በስድስት ወር", "ጸጋዬ ገብረ", "የጉድጓዱ ምስጢር", 
    "ገዳሙ ገዛኸኝ", "ደገልሃን", "ጌታቸው ጳውሎስ", "አዜብ", "መስፍን ሀብተማርያም", "የደም ዕንባ", 
    "ዳዊት ወልደጊዮርጊስ", "ኤርሚያስ አመልጋ", "ስሞተኛው", "ይኩኖ", "ቴዎድሮስ እስከ ቀዳማዊ", 
    "ተክለጻድቅ መኩርያ", "ልብወለድ", "ልቦለድ", "fiction", "novel", "ዳንኤል ክብረት",
    "goodamharicbooks", "kooblife", "እፍታ", "ደስፔንዛ", "አእምሮህ", "ገብረ-ክርስቶሰ ደስታ",
    "የሰርቆ_አደሮች", "ፍቅርና ሀገር"
]

def is_strictly_secular_or_fiction(text: str) -> bool:
    t = text.lower()
    for r in EXPLICIT_REJECT:
        if r in t:
            return True
    return False

async def main():
    await telegram_manager.init_client()
    client = telegram_manager.client
    dest_entity = await client.get_entity(TARGET_CHANNEL_LINK)
    print(f"Connected to {getattr(dest_entity, 'title', '')}")

    to_delete = []
    titles = []

    print("Scanning last 300 messages for secular/fiction...")
    async for msg in client.iter_messages(dest_entity, limit=300):
        fn = ""
        if msg.document:
            for attr in msg.document.attributes:
                if hasattr(attr, "file_name"):
                    fn = attr.file_name
                    break
        combined = f"{fn} {msg.text or ''}".lower()
        if is_strictly_secular_or_fiction(combined):
            to_delete.append(msg.id)
            titles.append(fn or f"Msg ID {msg.id}")
            print(f"❌ Target to delete: {fn}")

    if to_delete:
        print(f"\nDeleting {len(to_delete)} secular/fiction messages...")
        # በባች መሰረዝ
        batch_size = 50
        for i in range(0, len(to_delete), batch_size):
            chunk = to_delete[i:i + batch_size]
            await client.delete_messages(dest_entity, chunk)
            await asyncio.sleep(0.5)
        print(f"✅ Successfully deleted all {len(to_delete)} secular/political/fiction files!")
    else:
        print("No secular or fiction files found.")

if __name__ == "__main__":
    asyncio.run(main())
