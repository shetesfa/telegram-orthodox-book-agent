import os
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from app.telegram.client import telegram_manager
from app.database import (
    is_file_processed,
    record_processed_file,
    get_settings
)
from app.books.gemini_verifier import ensure_book_verified_before_output
from app.config import logger

async def send_book_to_saved_messages(
    candidate: Dict[str, Any],
    requested_title: str,
    author: str = "",
    confidence: float = 0.0,
    force_resend: bool = False,
    book_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Forwards candidate document to Telegram Saved Messages ('me') or target channel
    with Pre-Output Hybrid Verification Gate and Zero-Download Cloud Forwarding.
    """
    client = telegram_manager.client
    if not client or not client.is_connected() or not await client.is_user_authorized():
        return {"success": False, "error": "Telegram client not connected or unauthorized"}

    chat_id = candidate["telegram_chat_id"]
    message_id = candidate["message_id"]
    filename = candidate["filename"]
    source_name = candidate.get("chat_name", "Unknown")

    # Duplicate check
    settings = await get_settings()
    skip_duplicates = settings.get("skip_duplicates", True)

    if skip_duplicates and not force_resend:
        already_done = await is_file_processed(chat_id, message_id, filename)
        if already_done:
            logger.info("Duplicate file detected: %s (Chat %s, Msg %s). Skipping.", filename, chat_id, message_id)
            return {"success": True, "status": "duplicate_skipped", "message": "Duplicate skipped"}

    try:
        # 1. Fetch source message without downloading file
        src_msg = await client.get_messages(chat_id, ids=message_id)
        if not src_msg or not src_msg.media:
            return {"success": False, "error": "Original message or file no longer accessible"}

        # 2. Extract lightweight ~15KB thumbnail if available (takes <0.2s)
        thumb_bytes = None
        if hasattr(src_msg, "document") and src_msg.document and getattr(src_msg.document, "thumbs", None):
            try:
                thumb_bytes = await client.download_media(src_msg, file=bytes, thumb=-1)
            except Exception as te:
                logger.debug("Thumbnail download skipped: %s", te)

        # 3. PRE-OUTPUT GATE: Verify before any forwarding
        is_valid, verdict = await ensure_book_verified_before_output(
            title=requested_title or candidate.get("title", ""),
            filename=filename,
            caption=src_msg.text or candidate.get("caption", ""),
            source_channel_title=source_name,
            thumb_bytes=thumb_bytes,
            book_id=book_id
        )

        if not is_valid:
            logger.warning("🚫 [Pre-Output Blocked in sender.py] '%s': %s", filename, verdict.get("reason"))
            return {
                "success": False,
                "status": "rejected",
                "error": f"Blocked by verification: {verdict.get('reason')}",
                "category": verdict.get("category", "Rejected")
            }

        # 4. Prepare caption
        caption_text = (
            "📚 Book Collected\n\n"
            f"Title: {requested_title or filename}\n"
            f"Author: {author or 'Unknown'}\n"
            f"Filename: {filename}\n"
            f"Source: {source_name}\n"
            f"Confidence: {confidence:.0f}%\n"
            f"Verified By: {verdict.get('verified_by', 'hybrid')}\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d')}"
        )

        # 5. Resolve target destination
        dest_target = settings.get("target_channel") or "https://t.me/atsedeteguhan"
        try:
            dest_entity = await client.get_entity(dest_target)
        except Exception as ent_err:
            logger.warning("Could not resolve target channel '%s', falling back to 'me': %s", dest_target, ent_err)
            dest_entity = "me"

        # 6. ZERO-DOWNLOAD CLOUD FORWARDING: Server-side Telegram transfer in <0.4s
        logger.info("⚡ Cloud forwarding '%s' to target destination...", filename)
        try:
            await client.send_file(
                dest_entity,
                file=src_msg.media,
                caption=caption_text,
                force_document=True
            )
        except Exception as cloud_err:
            logger.info("Direct cloud file send fallback to forward_messages: %s", cloud_err)
            await client.forward_messages(dest_entity, messages=src_msg)

        # 7. Record in database
        await record_processed_file(
            requested_title=requested_title or filename,
            author=author or "Unknown",
            source=source_name,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            filename=filename,
            file_size=candidate.get("file_size", 0),
            confidence=confidence,
            status="sent",
            file_hash=""
        )

        logger.info("✅ Book '%s' successfully forwarded via Telegram Cloud.", requested_title or filename)
        return {"success": True, "status": "sent", "filename": filename}

    except Exception as e:
        logger.error("Failed to forward book: %s", e)
        return {"success": False, "error": str(e)}
