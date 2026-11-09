import os
import sys
import asyncio
import sqlite3
import argparse
from typing import List, Dict, Any
from telethon import errors
from telethon.tl.types import DocumentAttributeFilename

from app.config import DATABASE_PATH, TARGET_CHANNEL_LINK, logger
from app.books.classifier import classify_book_locally, normalize_amharic
from app.books.gemini_verifier import verify_book_hybrid_async, verify_books_batch_with_gemini
from app.telegram.client import telegram_manager
from app.telegram.harvester import orthodox_harvester

async def run_clean_db():
    """
    Subcommand: clean-db
    Audits every record in books.db using the fast Hybrid Classifier.
    Marks any Fiction, Scientific/Academic, or Secular entry as is_orthodox = 0.
    """
    logger.info("Starting Database Audit & Clean on: %s", DATABASE_PATH)
    if not os.path.exists(DATABASE_PATH):
        print(f"[ERROR] Database file not found at {DATABASE_PATH}")
        return

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # 1. Audit books_requested
        print("\n--- Auditing 'books_requested' table ---")
        cursor.execute("SELECT id, title, author FROM books_requested")
        requested_rows = cursor.fetchall()

        req_updated = 0
        for bid, title, author in requested_rows:
            local = classify_book_locally(title=title)
            if local["category"] in ("Fiction", "Scientific/Academic", "Other_Religion", "Secular"):
                cursor.execute("""
                    UPDATE books_requested 
                    SET is_orthodox = 0, status = 'rejected', book_category = ?, verification_reason = ?, verified_by = 'rejected', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (local["category"], local["reason"], bid))
                req_updated += 1
                logger.info("🚫 Blocked in books_requested: '%s' -> %s", title, local["category"])

        # 2. Audit processed_files
        print("\n--- Auditing 'processed_files' table ---")
        cursor.execute("SELECT id, requested_title, filename FROM processed_files")
        processed_rows = cursor.fetchall()

        proc_updated = 0
        for pid, req_title, filename in processed_rows:
            local = classify_book_locally(title=req_title or "", filename=filename or "")
            if local["category"] in ("Fiction", "Scientific/Academic", "Other_Religion", "Secular"):
                cursor.execute("""
                    UPDATE processed_files 
                    SET status = 'rejected_fiction', confidence = 0.0
                    WHERE id = ?
                """, (pid,))
                proc_updated += 1
                logger.info("🚫 Blocked in processed_files: '%s' / '%s' -> %s", req_title, filename, local["category"])

        conn.commit()

    print("\n✅ Database Clean Complete:")
    print(f" - books_requested: {req_updated} non-orthodox entries blocked")
    print(f" - processed_files: {proc_updated} non-orthodox entries blocked")

async def run_clean_channel(dry_run: bool = False, limit: int = 500):
    """
    Subcommand: clean-channel
    Scans TARGET_CHANNEL_LINK for non-orthodox files using the Hybrid Classifier
    and deletes them from the Telegram channel.
    """
    client = telegram_manager.client
    if not client:
        print("[ERROR] Telegram client not initialized.")
        return

    await client.connect()
    if not await client.is_user_authorized():
        print("[ERROR] Telegram client not authorized. Run web UI to login first.")
        return

    logger.info("Scanning target channel '%s' (limit=%d, dry_run=%s)...", TARGET_CHANNEL_LINK, limit, dry_run)
    try:
        dest_entity = await client.get_entity(TARGET_CHANNEL_LINK)
    except Exception as e:
        print(f"[ERROR] Could not resolve target channel '{TARGET_CHANNEL_LINK}': {e}")
        return

    to_delete_ids = []
    analyzed_count = 0
    blocked_count = 0

    try:
        async for msg in client.iter_messages(dest_entity, limit=limit):
            if not msg.document:
                continue

            analyzed_count += 1
            filename = ""
            for attr in msg.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

            caption = msg.text or ""
            # Fast Local Check first
            local = classify_book_locally(filename=filename, caption=caption)
            is_bad = local["category"] in ("Fiction", "Scientific/Academic", "Other_Religion", "Secular")
            reason = local["reason"]

            # If ambiguous, check thumbnail
            if not is_bad and local["score"] < 40.0:
                thumb_bytes = None
                if getattr(msg.document, "thumbs", None):
                    try:
                        thumb_bytes = await client.download_media(msg, file=bytes, thumb=-1)
                    except Exception:
                        pass
                verdict = await verify_book_hybrid_async(
                    title="",
                    filename=filename,
                    caption=caption,
                    thumb_bytes=thumb_bytes
                )
                if not verdict.get("is_orthodox", False):
                    is_bad = True
                    reason = verdict.get("reason", "Not authentic Orthodox book")

            if is_bad:
                blocked_count += 1
                to_delete_ids.append(msg.id)
                print(f"[FOUND NON-ORTHODOX] Msg ID {msg.id}: '{filename}' -> Reason: {reason}")

        print(f"\nAnalysis completed: {analyzed_count} files analyzed, {blocked_count} non-orthodox files identified.")

        if to_delete_ids:
            if dry_run:
                print(f"[DRY RUN] Would delete {len(to_delete_ids)} messages from channel. (No action taken).")
            else:
                print(f"Deleting {len(to_delete_ids)} messages from channel in batches...")
                batch_size = 50
                for i in range(0, len(to_delete_ids), batch_size):
                    chunk = to_delete_ids[i:i + batch_size]
                    try:
                        await client.delete_messages(dest_entity, chunk)
                        await asyncio.sleep(0.5)
                    except errors.FloodWaitError as fwe:
                        print(f"Flood wait {fwe.seconds}s...")
                        await asyncio.sleep(fwe.seconds + 1)
                print(f"✅ Successfully deleted {len(to_delete_ids)} non-orthodox messages from {TARGET_CHANNEL_LINK}.")
        else:
            print("✅ Channel is completely clean! No non-orthodox books detected.")

    except Exception as e:
        logger.error("Channel clean error: %s", e)
        print(f"[ERROR] Channel clean failed: {e}")

async def run_sweep_and_forward():
    """
    Subcommand: sweep-and-forward
    Harvests authentic EOTC books using the 3-stage Global Search and Hybrid Classifier.
    """
    print(f"Starting EOTC Book Harvester to: {TARGET_CHANNEL_LINK}...")
    res = await orthodox_harvester.start()
    print("Harvester Status:", res)
    while orthodox_harvester.is_running:
        status = orthodox_harvester.get_status()
        print(f"Progress: Forwarded {status['stats']['forwarded']} | Analyzed {status['stats']['analyzed']} | Rejected {status['stats']['rejected']}")
        await asyncio.sleep(5)

def main():
    parser = argparse.ArgumentParser(description="Telegram Orthodox Book Agent - Unified Maintenance CLI Tool")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to execute")

    # clean-db
    subparsers.add_parser("clean-db", help="Audit books.db and block any fiction/academic books")

    # clean-channel
    chan_parser = subparsers.add_parser("clean-channel", help="Scan and clean non-orthodox books from target Telegram channel")
    chan_parser.add_argument("--dry-run", action="store_true", help="Inspect only, do not delete messages")
    chan_parser.add_argument("--limit", type=int, default=500, help="Number of recent messages to scan (default: 500)")

    # sweep-and-forward
    subparsers.add_parser("sweep-and-forward", help="Run 3-stage global search and forward authentic EOTC books")

    args = parser.parse_args()

    if args.command == "clean-db":
        asyncio.run(run_clean_db())
    elif args.command == "clean-channel":
        asyncio.run(run_clean_channel(dry_run=args.dry_run, limit=args.limit))
    elif args.command == "sweep-and-forward":
        asyncio.run(run_sweep_and_forward())

if __name__ == "__main__":
    main()
