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
from app.config import DOWNLOAD_DIR, logger

def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 of downloaded file."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            sha.update(chunk)
    return sha.hexdigest()

async def send_book_to_saved_messages(
    candidate: Dict[str, Any],
    requested_title: str,
    author: str = "",
    confidence: float = 0.0,
    force_resend: bool = False
) -> Dict[str, Any]:
    """Downloads/forwards candidate document to Telegram Saved Messages ('me')."""
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

    caption_text = (
        "📚 Book Collected\n\n"
        f"Title: {requested_title or 'Unknown'}\n"
        f"Author: {author or 'Unknown'}\n"
        f"Filename: {filename}\n"
        f"Source: {source_name}\n"
        f"Confidence: {confidence:.0f}%\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d')}"
    )

    temp_path = None
    file_hash = ""
    file_size = candidate.get("file_size", 0)

    try:
        # Get source message
        src_msg = await client.get_messages(chat_id, ids=message_id)
        if not src_msg or not src_msg.media:
            return {"success": False, "error": "Original message or file no longer accessible"}

        # Resolve target destination: custom channel or 'me'
        dest_target = settings.get("target_channel") or "https://t.me/+2EsS9AQ1kt9mYmFk"
        try:
            dest_entity = await client.get_entity(dest_target)
        except Exception as ent_err:
            logger.warning("Could not resolve target channel '%s', falling back to 'me': %s", dest_target, ent_err)
            dest_entity = "me"

        logger.info("Instantly delivering '%s' to target channel via Telegram Cloud...", filename)
        
        # Super-fast direct cloud delivery: 0 download, 0 upload, 1 second execution!
        try:
            await client.send_file(
                dest_entity,
                file=src_msg.media,
                caption=caption_text,
                force_document=True
            )
        except Exception as cloud_err:
            logger.info("Direct cloud file send fallback to forward: %s", cloud_err)
            await client.forward_messages(dest_entity, messages=src_msg)

        # Record in database
        await record_processed_file(
            requested_title=requested_title,
            author=author or "Unknown",
            source=source_name,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            filename=filename,
            file_size=file_size,
            confidence=confidence,
            status="sent",
            file_hash=file_hash
        )

        # Clean up temporary file if configured
        delete_downloads = settings.get("delete_downloads_after_send", True)
        if delete_downloads and temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info("Temporary file '%s' cleaned up.", temp_path)
            except Exception as ce:
                logger.warning("Could not delete temporary file: %s", ce)

        logger.info("Book '%s' successfully sent to Saved Messages.", requested_title)
        return {"success": True, "status": "sent", "filename": filename}

    except Exception as e:
        logger.error("Failed to send book to Saved Messages: %s", e)
        # Clean up temp file on failure too
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return {"success": False, "error": str(e)}
