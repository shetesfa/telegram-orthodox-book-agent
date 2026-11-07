from typing import List, Dict, Any, Optional
from telethon.tl.types import (
    InputMessagesFilterDocument,
    DocumentAttributeFilename,
    Channel,
    Chat
)
from app.telegram.client import telegram_manager
from app.database import get_enabled_sources, sync_sources, get_settings
from app.config import logger

async def discover_telegram_sources() -> List[Dict[str, Any]]:
    """Discover all chats/channels authorized for this Telegram account."""
    client = telegram_manager.client
    if not client or not client.is_connected() or not await client.is_user_authorized():
        return []

    sources = []
    try:
        dialogs = await client.get_dialogs(limit=200)
        for d in dialogs:
            entity = d.entity
            chat_type = "chat"
            username = getattr(entity, "username", None) or ""
            
            if isinstance(entity, Channel):
                chat_type = "channel" if entity.broadcast else "supergroup"
            elif isinstance(entity, Chat):
                chat_type = "group"
            elif getattr(entity, "bot", False):
                continue  # Skip bots

            source_item = {
                "chat_id": d.id,
                "name": d.name or f"Chat {d.id}",
                "username": username,
                "type": chat_type
            }
            sources.append(source_item)

        await sync_sources(sources)
        logger.info("Discovered %d legitimate Telegram sources.", len(sources))
        return sources
    except Exception as e:
        logger.error("Error discovering Telegram sources: %s", e)
        return []

async def search_documents_globally(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Search Telegram globally across public chats, channels, and global library repositories.
    Uses Telethon MTProto global message search when entity is None.
    """
    client = telegram_manager.client
    if not client or not client.is_connected() or not await client.is_user_authorized():
        return []

    settings = await get_settings()
    allowed_exts = [ext.strip().lower() for ext in str(settings.get("allowed_extensions", "pdf,epub,mobi,djvu")).split(",")]
    max_size_mb = float(settings.get("max_file_size_mb", 500))
    max_size_bytes = max_size_mb * 1024 * 1024

    candidates = []
    try:
        logger.info("Executing global Telegram document search for query: '%s'...", query)
        async for msg in client.iter_messages(
            None,
            search=query,
            filter=InputMessagesFilterDocument,
            limit=limit
        ):
            if not msg.document:
                continue

            file_size = msg.document.size or 0
            if max_size_mb > 0 and file_size > max_size_bytes:
                continue

            filename = ""
            for attr in msg.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

            if not filename:
                ext = msg.file.ext or ".pdf"
                filename = f"document_{msg.id}{ext}"

            file_ext = filename.split(".")[-1].lower() if "." in filename else ""
            if allowed_exts and file_ext not in allowed_exts:
                continue

            chat_id = msg.chat_id
            chat_name = "Telegram Global Search"
            try:
                chat_entity = await msg.get_chat()
                chat_name = getattr(chat_entity, "title", None) or getattr(chat_entity, "username", "") or str(chat_id)
            except Exception:
                pass

            candidates.append({
                "telegram_chat_id": chat_id,
                "chat_name": chat_name,
                "message_id": msg.id,
                "filename": filename,
                "file_size": file_size,
                "caption": msg.text or "",
                "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
                "file_type": file_ext.upper(),
                "mime_type": msg.document.mime_type
            })
    except Exception as e:
        logger.warning("Error performing global Telegram search for '%s': %s", query, e)

    return candidates

async def search_documents_in_sources(query: str, chat_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """Search for document files matching query in enabled authorized sources, with global search fallback."""
    client = telegram_manager.client
    if not client or not client.is_connected() or not await client.is_user_authorized():
        return []

    settings = await get_settings()
    search_limit = int(settings.get("search_limit_per_chat", 100))
    allowed_exts = [ext.strip().lower() for ext in str(settings.get("allowed_extensions", "pdf,epub,mobi,djvu")).split(",")]
    max_size_mb = float(settings.get("max_file_size_mb", 500))
    max_size_bytes = max_size_mb * 1024 * 1024
    enable_global = bool(settings.get("enable_global_search", True))

    if chat_ids is None:
        enabled_sources = await get_enabled_sources()
        target_chat_ids = [s["chat_id"] for s in enabled_sources]
    else:
        target_chat_ids = chat_ids

    candidates = []

    # 1. Primary: Global Telegram Document Search (Fastest & most comprehensive across all public channels)
    if enable_global:
        try:
            logger.info("Executing Primary Global Telegram Document Search for: '%s'...", query)
            global_results = await search_documents_globally(query, limit=50)
            candidates.extend(global_results)
            logger.info("Global Search found %d candidates for '%s'.", len(global_results), query)
        except Exception as ge:
            logger.warning("Global Search encountered error: %s", ge)

    # 2. Secondary: Only if zero candidates found globally, check first 5 local enabled sources
    if not candidates and target_chat_ids:
        logger.info("No global candidates found. Checking up to 5 local enabled sources...")
        for chat_id in target_chat_ids[:5]:
            try:
                entity = await client.get_input_entity(chat_id)
                chat_name = str(chat_id)
                try:
                    full_chat = await client.get_entity(entity)
                    chat_name = getattr(full_chat, "title", None) or getattr(full_chat, "first_name", "") or str(chat_id)
                except Exception:
                    pass

                async for msg in client.iter_messages(
                    entity,
                    search=query,
                    filter=InputMessagesFilterDocument,
                    limit=search_limit
                ):
                    if not msg.document:
                        continue

                    file_size = msg.document.size or 0
                    if max_size_mb > 0 and file_size > max_size_bytes:
                        continue

                    filename = ""
                    for attr in msg.document.attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            filename = attr.file_name
                            break
                    
                    if not filename:
                        ext = msg.file.ext or ".pdf"
                        filename = f"document_{msg.id}{ext}"

                    file_ext = filename.split(".")[-1].lower() if "." in filename else ""
                    if allowed_exts and file_ext not in allowed_exts:
                        continue

                    # Avoid duplicate message IDs
                    if any(c["telegram_chat_id"] == chat_id and c["message_id"] == msg.id for c in candidates):
                        continue

                    candidates.append({
                        "telegram_chat_id": chat_id,
                        "chat_name": chat_name,
                        "message_id": msg.id,
                        "filename": filename,
                        "file_size": file_size,
                        "caption": msg.text or "",
                        "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
                        "file_type": file_ext.upper(),
                        "mime_type": msg.document.mime_type
                    })
            except Exception as e:
                logger.warning("Error searching in chat %s: %s", chat_id, e)
                continue

    logger.info("Found %d total candidates for query '%s'", len(candidates), query)
    return candidates
