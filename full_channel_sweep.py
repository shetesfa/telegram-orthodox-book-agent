import asyncio
import sys
import re

sys.stdout.reconfigure(encoding="utf-8")

from app.telegram.client import telegram_manager

TARGET_CHANNEL_LINK = "https://t.me/+2EsS9AQ1kt9mYmFk"

# 1. በእርግጠኝነት በቻናሉ እንዲቆዩ የሚፈቀዱ የኦርቶዶክስ ተዋሕዶ መንፈሳዊ ቃላት (Strict Whitelist)
LEGIT_ORTHODOX_PATTERNS = [
    "ገድለ", "ገድሊ", "ድርሳነ", "ድርሳን", "አንድምታ", "ትርጓሜ", "ትርጓሜያት", 
    "ቅዳሴ", "ውዳሴ ማርያም", "ውዳሴ", "ሰዓታት", "ጾመ ድጓ", "ድጓ", "ዝማሬ", "መዋሥዕት", 
    "ሥርዓተ ማኅሌት", "ማኅሌት", "አቋቋም", "ቅዱስ ያሬድ", "ያሬድ",
    "ሃይማኖተ አበው", "ፍትሐ ነገሥት", "መጽሐፈ ምስጢር", "ስንክሳር", "ባሕረ ሐሳብ",
    "መጽሐፈ ገነት", "ዜና አበው", "ማር ይስሐቅ", "ፊልክስዩስ", "አረጋዊ መንፈሳዊ",
    "መልክአ", "መልክዐ", "አርጋኖን", "ሰይፈ ሥላሴ", "ተአምረ ማርያም", "ተአምረ ኢየሱስ",
    "መጽሐፍ ቅዱስ", "መፅሐፍ ቅዱስ", "መዝሙረ ዳዊት", "የዳዊት መዝሙር", "ወንጌል",
    "ኦሪት", "ነገረ ማርያም", "ነገረ ድኅነት", "ነገረ ክርስቶስ", "አቡነ ተክለ",
    "አቡነ አቢብ", "ቅዱስ ጊዮርጊስ", "ቅዱስ ሩፋኤል", "ቅዱስ ሚካኤል", "ቅዱስ ገብርኤል",
    "ምስጋና ሕይወት", "ዮሐንስ አፈወርቅ", "መጽሐፈ ኪዳን", "ትምህርተ ኅቡዓት",
    "ፍትሐት", "homilies", "orthodox", "eotc"
]

# 2. በፍጹም በኦርቶዶክስ ቻናል የማይፈቀዱ (Secular / Fiction / Authors)
STRICT_BLACKLIST = [
    "አርዐያ", "ከበደ ሚካኤል", "ገብረሃና", "ገብረ ሐና", "ባይከዳኝ", "ሱስንዮስ", "አለመኖር",
    "ሌቱም_አይነጋልኝ", "ስብሀት", "ስብሐት", "ያዕቆብ_ኃይለማርያም", "አሰብ", "ኅሩይ ወልደ",
    "ወንጀል እና ቅጣት", "ዶስቶየቭስኪ", "በርታ ክሌይ", "የውበት ወጥመድ", "ልብወለድ", "ልቦለድ",
    "ትኩሳት", "ቆርጠሀት", "ያገር ልጅ", "በራስ መተማመን", "የተናቁ ዕንቁዎች", "ጠያይም መላእክት",
    "እኮ እንዴት", "የነጋሶ መንገድ", "ዳንኤል ተረፈ", "ሳይላክ የቀረ", "ህልፈተ አንጃ", "ኢህአፓ",
    "መንገድ ስጡኝ", "የከፍተኛ ትምህርት", "ጳውሎስ ኞኞ", "ሀሁ በስድስት ወር", "ጸጋዬ ገብረ",
    "የጉድጓዱ ምስጢር", "ገዳሙ ገዛኸኝ", "ደገልሃን", "ጌታቸው ጳውሎስ", "አዜብ", "መስፍን ሀብተማርያም",
    "የደም ዕንባ", "ዳዊት ወልደጊዮርጊስ", "ኤርሚያስ አመልጋ", "ስሞተኛው", "ይኩኖ", "ቴዎድሮስ እስከ ቀዳማዊ",
    "ተክለጻድቅ መኩርያ", "መንግስቱ ኃይለ", "ትግላችን", "የቡርቃ_ዝምታ", "ተስፋዬ ገብረአብ", "ማፊያ",
    "ወዳጄነህ", "ምኒልክ", "ዳንኤል ክብረት", "goodamharicbooks", "kooblife", "እፍታ", "ደስፔንዛ",
    "አእምሮህ", "ገብረ-ክርስቶሰ ደስታ", "የሰርቆ_አደሮች", "ፍቅርና ሀገር", "ፍቅር", "ግጥም", "ልቦለድ"
]

def is_strictly_orthodox_spiritual(filename: str, caption: str) -> bool:
    text = f"{filename} {caption}".lower()

    # Blacklist ውስጥ ካለ ወዲያውኑ ውድቅ
    for b in STRICT_BLACKLIST:
        if b in text:
            # ፍቅረ እግዚአብሔር፣ ፍቅረ መስቀል እንዳይጣሉ
            if b == "ፍቅር" and any(k in text for k in ["ፍቅረ እግዚአብሔር", "ፍቅረ መስቀል", "ፍቅረ ቅዱሳን"]):
                continue
            return False

    # Whitelist ውስጥ ቢያንስ አንዱ መኖር አለበት
    for w in LEGIT_ORTHODOX_PATTERNS:
        if w in text:
            return True

    return False

async def sweep_and_clean():
    await telegram_manager.init_client()
    client = telegram_manager.client
    dest_entity = await client.get_entity(TARGET_CHANNEL_LINK)
    channel_title = getattr(dest_entity, "title", "")
    print(f"=== Starting Full Channel Audit for '{channel_title}' ===")

    to_delete = []
    retained = []

    # በቻናሉ ውስጥ ያሉትን ሁሉንም መልእክቶች እንቃኝ
    async for msg in client.iter_messages(dest_entity, limit=400):
        # ጽሑፍ ብቻ የሆኑ ወይም ሰነድ የሌላቸውን እናልፋለን (ለምሳሌ የቻናል መግለጫ)
        if not msg.document:
            continue

        fn = ""
        for attr in msg.document.attributes:
            if hasattr(attr, "file_name"):
                fn = attr.file_name
                break
        caption = msg.text or ""

        if is_strictly_orthodox_spiritual(fn, caption):
            retained.append((msg.id, fn))
        else:
            to_delete.append((msg.id, fn))
            print(f"🗑 MARKED FOR DELETION: {fn}")

    print(f"\nAudit Summary:")
    print(f"  - Legitimate Orthodox Spiritual Books Kept: {len(retained)}")
    print(f"  - Non-Orthodox / Fiction / Secular Books to Delete: {len(to_delete)}")

    if to_delete:
        print(f"\nDeleting {len(to_delete)} messages from channel...")
        ids_only = [msg_id for msg_id, _ in to_delete]
        batch_size = 50
        for i in range(0, len(ids_only), batch_size):
            chunk = ids_only[i:i + batch_size]
            await client.delete_messages(dest_entity, chunk)
            await asyncio.sleep(0.8)
        print("✅ Full channel cleanup completed successfully!")

if __name__ == "__main__":
    asyncio.run(sweep_and_clean())
