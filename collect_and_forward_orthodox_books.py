import asyncio
import sys
import re
from typing import Set

# UTF-8 for Windows console
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from telethon.tl.types import InputMessagesFilterDocument, DocumentAttributeFilename
from app.telegram.client import telegram_manager
from app.database import init_db, is_file_processed, record_processed_file
from app.config import logger

TARGET_CHANNEL_LINK = "https://t.me/+2EsS9AQ1kt9mYmFk"

# Targeted Orthodox Channels in user's account & public domain
ORTHODOX_CHANNELS = [
    "@EOTCBooks1",            # EOTC Books ⛪️
    "@menfesawimetshahft",     # መንፈሳዊ መጽሐፍ በpdf
    "@zikirekdusn",           # ዝክረ ቅዱሳን ማኅበረ ቅዱስ ዳዊት
    "@and_metshaf",           # ፩ መጽሐፍ
    "@Amharic_Book",          # Amharic Books
    "@goodamharicbooks",      # Good amharic books
    "@kooblife",              # ETHIO BOOKS PDF
]

# Strict Orthodox Keywords to accept
ORTHODOX_KEYWORDS = [
    "ገድል", "ድርሳን", "አንድምታ", "ትርጓሜ", "ቅዳሴ", "ውዳሴ", "ሰዓታት", "ድጓ", 
    "ጾመ", "ምዕራፍ", "ዝማሬ", "መዋሥዕት", "ነገረ", "ሃይማኖተ", "ክብረ", "ተአምረ",
    "ብሉያት", "ሐዲሳት", "ወንጌል", "ጳውሎስ", "መዝሙረ", "ዳዊት", "ሲራክ", "ሔኖክ", 
    "ኢሳይያስ", "ኤርሚያስ", "ሕዝቅኤል", "መቃብያን", "መጽሐፈ", "ፍትሐ", "ነገሥት",
    "ስንክሳር", "ሃይማኖት", "ተዋሕዶ", "ኦርቶዶክስ", "ቤተክርስቲያን", "ማኅበረ ቅዱሳን",
    "ዝክረ", "ቅዱሳን", "ምስጢረ", "ዜና", "ቅዱስ", "ቅድስት", "አቡነ", "ማርያም", "ማሪያም"
]

# Words to strictly reject (fiction, politics, magazines, etc.)
REJECT_KEYWORDS = [
    "ልብወለድ", "ልቦለድ", "fiction", "novel", "ታሪካዊ ልብወለድ", "ፍቅር", "የፍቅር", 
    "ዘፈን", "ሙዚቃ", "ፖለቲካ", "መጽሔት", "ጋዜጣ", "ወሬ", "ስፖርት", "እግር ኳስ"
]

def is_orthodox_book(filename: str, caption: str) -> bool:
    """Analyze filename and caption to strictly confirm legitimate Orthodox spiritual book."""
    text = (filename + " " + caption).lower()
    
    # 1. Reject fiction and unrelated
    for r in REJECT_KEYWORDS:
        if r in text:
            if r in ("ፍቅር", "የፍቅር") and any(holy in text for holy in ("ፍቅረ እግዚአብሔር", "ፍቅረ መስቀል", "ፍቅረ ቅዱሳን")):
                continue
            return False

    # 2. Must match at least one Orthodox keyword
    for k in ORTHODOX_KEYWORDS:
        if k in text:
            return True

    return False

async def harvest_and_forward():
    await init_db()
    await telegram_manager.init_client()
    client = telegram_manager.client

    if not client or not await client.is_user_authorized():
        print("Error: Telegram client is not authorized. Please connect first.")
        return

    # 1. Resolve target channel
    print(f"Connecting to target channel: {TARGET_CHANNEL_LINK}...")
    try:
        dest_entity = await client.get_entity(TARGET_CHANNEL_LINK)
        dest_title = getattr(dest_entity, "title", str(dest_entity.id))
        print(f"Target destination verified: '{dest_title}' (ID: {dest_entity.id})")
    except Exception as e:
        print(f"Failed to access target channel: {e}")
        return

    print("=" * 60)
    print("Starting Orthodox Books Analysis and Direct Cloud Forwarding...")
    print("=" * 60)

    total_forwarded = 0
    total_analyzed = 0
    total_duplicates = 0
    total_rejected = 0

    for channel_ref in ORTHODOX_CHANNELS:
        print(f"\nScanning channel: {channel_ref}...")
        try:
            chat_entity = await client.get_entity(channel_ref)
            chat_title = getattr(chat_entity, "title", channel_ref)
        except Exception as ce:
            print(f"Could not open channel {channel_ref}: {ce}")
            continue

        print(f"Analyzing documents in '{chat_title}'...")

        # Stream documents from channel
        async for msg in client.iter_messages(chat_entity, filter=InputMessagesFilterDocument, limit=500):
            if not msg.document:
                continue

            total_analyzed += 1

            # Extract filename
            filename = ""
            for attr in msg.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

            if not filename:
                ext = msg.file.ext or ".pdf"
                filename = f"orthodox_book_{msg.id}{ext}"

            # Only accept PDF, EPUB, DJVU
            ext = filename.split(".")[-1].lower() if "." in filename else ""
            if ext not in ("pdf", "epub", "djvu"):
                continue

            caption = msg.text or ""

            # Check if legitimate Orthodox book
            if not is_orthodox_book(filename, caption):
                total_rejected += 1
                continue

            # Duplicate check in database
            already_done = await is_file_processed(msg.chat_id, msg.id, filename)
            if already_done:
                total_duplicates += 1
                continue

            clean_title = re.sub(r"\.(pdf|epub|djvu)$", "", filename, flags=re.IGNORECASE).replace("_", " ").strip()

            caption_text = (
                "⛪️ ኦርቶዶክሳዊ መጽሐፍ\n\n"
                f"📖 ርዕስ: {clean_title}\n"
                f"📁 ፋይል: {filename}\n"
                f"📡 ምንጭ: {chat_title}\n"
                f"📅 ቀን: {msg.date.strftime('%Y-%m-%d') if msg.date else ''}\n\n"
                "✨ ለ @ortodox_book_atsedeteguhan የተሰበሰበ"
            )

            # Direct Instant Cloud Transfer
            try:
                await client.send_file(
                    dest_entity,
                    file=msg.media,
                    caption=caption_text,
                    force_document=True
                )
                total_forwarded += 1

                # Record in database to prevent future duplicates
                await record_processed_file(
                    requested_title=clean_title,
                    author="Orthodox Church",
                    source=chat_title,
                    telegram_chat_id=msg.chat_id,
                    telegram_message_id=msg.id,
                    filename=filename,
                    file_size=msg.document.size or 0,
                    confidence=100.0,
                    status="sent"
                )

                print(f"[{total_forwarded}] ✅ Forwarded: {filename} (from {chat_title})")

                # Throttle slightly to stay well within Telegram flood limits
                await asyncio.sleep(1.8)

            except Exception as fe:
                print(f"Error forwarding {filename}: {fe}")
                # Back off if flood wait occurs
                if "flood" in str(fe).lower():
                    print("Flood wait detected, sleeping for 30s...")
                    await asyncio.sleep(30)

    print("\n" + "=" * 60)
    print("Orthodox Books Collection Complete!")
    print(f"Total Analyzed: {total_analyzed}")
    print(f"Total Legitimate Forwarded: {total_forwarded}")
    print(f"Total Duplicates Skipped: {total_duplicates}")
    print(f"Total Rejected (Non-Orthodox/Fiction): {total_rejected}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(harvest_and_forward())
