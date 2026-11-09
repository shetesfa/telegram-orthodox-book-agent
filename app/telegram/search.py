import asyncio
import re
from typing import List, Dict, Any, Optional, Set
from telethon import functions, errors
from telethon.tl.types import (
    InputMessagesFilterDocument,
    DocumentAttributeFilename,
    Channel,
    Chat
)
from app.telegram.client import telegram_manager
from app.database import get_enabled_sources, sync_sources, get_settings
from app.books.classifier import normalize_amharic
from app.config import logger

# Amharic homophone variant generator
HOMOPHONE_PAIRS = [
    ('ሀ', 'ሐ'), ('ሐ', 'ሀ'), ('ኀ', 'ሀ'), ('ሁ', 'ሑ'), ('ሑ', 'ሁ'),
    ('ሂ', 'ሒ'), ('ሒ', 'ሂ'), ('ሃ', 'ሓ'), ('ሓ', 'ሃ'), ('ሄ', 'ሔ'),
    ('ህ', 'ሕ'), ('ሕ', 'ህ'), ('ሆ', 'ሖ'), ('ሰ', 'ሠ'), ('ሠ', 'ሰ'),
    ('ሱ', 'ሡ'), ('ሲ', 'ሢ'), ('ሳ', 'ሣ'), ('ሴ', 'ሤ'), ('ስ', 'ሥ'),
    ('ሥ', 'ስ'), ('ሶ', 'ሦ'), ('አ', 'ዐ'), ('ዐ', 'አ'), ('ኡ', 'ዑ'),
    ('ኢ', 'ዒ'), ('ኣ', 'ዓ'), ('ዓ', 'አ'), ('እ', 'ዕ'), ('ዕ', 'እ'),
    ('ኦ', 'ዖ'), ('ጸ', 'ፀ'), ('ፀ', 'ጸ'), ('ጹ', 'ፁ'), ('ጺ', 'ፂ'),
    ('ጻ', 'ፃ'), ('ጼ', 'ፄ'), ('ጽ', 'ፅ'), ('ፅ', 'ጽ'), ('ጾ', 'ፆ')
]

# EOTC Discovery Keywords for Stage 3
EOTC_DISCOVERY_QUERIES = [
    "ኦርቶዶክስ መጻሕፍት",
    "ተዋሕዶ መጻሕፍት",
    "Orthodox Tewahedo books"
]

def generate_amharic_variants(query: str) -> List[str]:
    """Generates alternative Amharic spelling variants (e.g. ተዋሕዶ <-> ተዋህዶ, ስንክሳር <-> ሥንክሳር)."""
    variants = set()
    cleaned = query.strip()
    if not cleaned:
        return []

    # Variant 1: Completely homophone-normalized
    norm = normalize_amharic(cleaned)
    if norm and norm != cleaned.lower():
        variants.add(norm)

    # Variant 2: Simple character switches
    for char_a, char_b in HOMOPHONE_PAIRS:
        if char_a in cleaned:
            v = cleaned.replace(char_a, char_b)
            if v != cleaned:
                variants.add(v)
                break

    return [v for v in variants if v and v.lower() != cleaned.lower()]

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
                continue

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
    except errors.FloodWaitError as fwe:
        logger.warning("FloodWait during source discovery: sleeping %ds", fwe.seconds)
        await asyncio.sleep(fwe.seconds + 1)
        return []
    except Exception as e:
        logger.error("Error discovering Telegram sources: %s", e)
        return []

async def _extract_candidate_from_message(
    msg: Any,
    allowed_exts: List[str],
    max_size_bytes: float,
    seen_doc_ids: Set[int],
    seen_msg_keys: Set[str]
) -> Optional[Dict[str, Any]]:
    """Helper to safely extract candidate metadata with deduplication and source channel resolution."""
    if not msg.document:
        return None

    # Deduplicate by document.id
    doc_id = msg.document.id
    if doc_id in seen_doc_ids:
        return None

    chat_id = msg.chat_id
    msg_key = f"{chat_id}:{msg.id}"
    if msg_key in seen_msg_keys:
        return None

    file_size = msg.document.size or 0
    if max_size_bytes > 0 and file_size > max_size_bytes:
        return None

    filename = ""
    for attr in getattr(msg.document, "attributes", []):
        if isinstance(attr, DocumentAttributeFilename):
            filename = attr.file_name
            break

    if not filename:
        ext = msg.file.ext or ".pdf"
        filename = f"document_{msg.id}{ext}"

    file_ext = filename.split(".")[-1].lower() if "." in filename else ""
    if allowed_exts and file_ext not in allowed_exts:
        return None

    # Resolve channel title
    source_channel_title = str(chat_id)
    try:
        chat_entity = await msg.get_chat()
        source_channel_title = (
            getattr(chat_entity, "title", None) or
            getattr(chat_entity, "username", "") or
            getattr(chat_entity, "first_name", "") or
            str(chat_id)
        )
    except Exception:
        pass

    seen_doc_ids.add(doc_id)
    seen_msg_keys.add(msg_key)

    return {
        "telegram_chat_id": chat_id,
        "chat_name": source_channel_title,
        "source_channel_title": source_channel_title,
        "message_id": msg.id,
        "document_id": doc_id,
        "filename": filename,
        "file_size": file_size,
        "caption": msg.text or "",
        "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
        "file_type": file_ext.upper(),
        "mime_type": msg.document.mime_type
    }

async def search_documents_globally(query: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    True 3-Stage Global Search:
    Stage 1: Dialog Global Search (iter_messages(None, search=query)).
    Stage 2: Amharic Normalized Variant Search (handles ሐ/ሀ, ጸ/ፀ, ሠ/ሰ variations).
    Stage 3: Public Channel Discovery via contacts.SearchRequest + deep search within public channels.
    Deduplicated by document.id and (chat_id, message.id).
    """
    client = telegram_manager.client
    if not client or not client.is_connected() or not await client.is_user_authorized():
        return []

    settings = await get_settings()
    allowed_exts = [ext.strip().lower() for ext in str(settings.get("allowed_extensions", "pdf,epub,mobi,djvu")).split(",")]
    max_size_mb = float(settings.get("max_file_size_mb", 500))
    max_size_bytes = max_size_mb * 1024 * 1024

    candidates: List[Dict[str, Any]] = []
    seen_doc_ids: Set[int] = set()
    seen_msg_keys: Set[str] = set()

    # --- STAGE 1: Dialog Global Search ---
    logger.info("🔍 [Global Search Stage 1] Searching across joined dialogs for: '%s'...", query)
    try:
        async for msg in client.iter_messages(
            None,
            search=query,
            filter=InputMessagesFilterDocument,
            limit=limit
        ):
            cand = await _extract_candidate_from_message(
                msg, allowed_exts, max_size_bytes, seen_doc_ids, seen_msg_keys
            )
            if cand:
                candidates.append(cand)
    except errors.FloodWaitError as fwe:
        logger.warning("FloodWait in Stage 1 search: sleeping %ds", fwe.seconds)
        await asyncio.sleep(fwe.seconds + 1)
    except Exception as e:
        logger.warning("Stage 1 search error: %s", e)

    # --- STAGE 2: Amharic Normalized / Variant Search ---
    variants = generate_amharic_variants(query)
    for variant in variants[:2]:
        logger.info("🔍 [Global Search Stage 2] Searching Amharic spelling variant: '%s'...", variant)
        try:
            async for msg in client.iter_messages(
                None,
                search=variant,
                filter=InputMessagesFilterDocument,
                limit=30
            ):
                cand = await _extract_candidate_from_message(
                    msg, allowed_exts, max_size_bytes, seen_doc_ids, seen_msg_keys
                )
                if cand:
                    candidates.append(cand)
        except errors.FloodWaitError as fwe:
            logger.warning("FloodWait in Stage 2 search: sleeping %ds", fwe.seconds)
            await asyncio.sleep(fwe.seconds + 1)
        except Exception as e:
            logger.warning("Stage 2 search error for variant '%s': %s", variant, e)

    # --- STAGE 3: Public Channel Discovery via contacts.SearchRequest ---
    # Only if candidates are sparse or to ensure comprehensive public reach
    discovered_channels = []
    search_terms = [query] + EOTC_DISCOVERY_QUERIES
    try:
        logger.info("🔍 [Global Search Stage 3] Discovering public channels via contacts.SearchRequest...")
        for q_term in search_terms[:2]:
            try:
                res = await client(functions.contacts.SearchRequest(q=q_term, limit=10))
                if hasattr(res, "chats"):
                    for chat in res.chats:
                        if isinstance(chat, Channel) and chat.broadcast:
                            discovered_channels.append(chat)
            except errors.FloodWaitError as fwe:
                logger.warning("FloodWait in contacts.SearchRequest: sleeping %ds", fwe.seconds)
                await asyncio.sleep(fwe.seconds + 1)
                break
            except Exception as se:
                logger.debug("contacts.SearchRequest for '%s' failed: %s", q_term, se)

        # Cache discovered channels in sources table
        if discovered_channels:
            new_sources = [{
                "chat_id": ch.id,
                "name": ch.title or f"Channel {ch.id}",
                "username": getattr(ch, "username", "") or "",
                "type": "channel"
            } for ch in discovered_channels]
            try:
                await sync_sources(new_sources)
            except Exception as dbe:
                logger.debug("Could not cache discovered sources: %s", dbe)

        # Deep search inside unique discovered public channels
        seen_channel_ids = set()
        for ch in discovered_channels:
            if ch.id in seen_channel_ids:
                continue
            seen_channel_ids.add(ch.id)

            try:
                async for msg in client.iter_messages(
                    ch,
                    search=query,
                    filter=InputMessagesFilterDocument,
                    limit=15
                ):
                    cand = await _extract_candidate_from_message(
                        msg, allowed_exts, max_size_bytes, seen_doc_ids, seen_msg_keys
                    )
                    if cand:
                        candidates.append(cand)
            except errors.FloodWaitError as fwe:
                logger.warning("FloodWait during channel deep search: sleeping %ds", fwe.seconds)
                await asyncio.sleep(fwe.seconds + 1)
            except Exception as ce:
                logger.debug("Error searching inside public channel '%s': %s", getattr(ch, "title", ch.id), ce)

    except Exception as e:
        logger.warning("Stage 3 public discovery error: %s", e)

    logger.info("✅ True Global Search completed: %d total deduplicated candidates for '%s'.", len(candidates), query)
    return candidates

async def search_documents_in_sources(query: str, chat_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """
    Search for document files matching query in enabled sources with global search deduplication.
    Guarantees no channel is scanned twice.
    """
    client = telegram_manager.client
    if not client or not client.is_connected() or not await client.is_user_authorized():
        return []

    settings = await get_settings()
    search_limit = int(settings.get("search_limit_per_chat", 100))
    allowed_exts = [ext.strip().lower() for ext in str(settings.get("allowed_extensions", "pdf,epub,mobi,djvu")).split(",")]
    max_size_mb = float(settings.get("max_file_size_mb", 500))
    max_size_bytes = max_size_mb * 1024 * 1024
    enable_global = bool(settings.get("enable_global_search", True))

    candidates: List[Dict[str, Any]] = []
    seen_doc_ids: Set[int] = set()
    seen_msg_keys: Set[str] = set()
    scanned_channels: Set[int] = set()

    # 1. Primary: True Global Search
    if enable_global:
        try:
            global_results = await search_documents_globally(query, limit=50)
            for cand in global_results:
                seen_doc_ids.add(cand.get("document_id", 0))
                seen_msg_keys.add(f"{cand['telegram_chat_id']}:{cand['message_id']}")
                candidates.append(cand)
        except Exception as ge:
            logger.warning("Primary Global Search error: %s", ge)

    # 2. Secondary: Enabled Local Sources (without scanning the same channel twice)
    if chat_ids is None:
        enabled_sources = await get_enabled_sources()
        target_chat_ids = [s["chat_id"] for s in enabled_sources]
    else:
        target_chat_ids = chat_ids

    for chat_id in target_chat_ids:
        if chat_id in scanned_channels:
            continue
        scanned_channels.add(chat_id)

        try:
            entity = await client.get_input_entity(chat_id)
            async for msg in client.iter_messages(
                entity,
                search=query,
                filter=InputMessagesFilterDocument,
                limit=search_limit
            ):
                cand = await _extract_candidate_from_message(
                    msg, allowed_exts, max_size_bytes, seen_doc_ids, seen_msg_keys
                )
                if cand:
                    candidates.append(cand)
        except errors.FloodWaitError as fwe:
            logger.warning("FloodWait in chat %s: sleeping %ds", chat_id, fwe.seconds)
            await asyncio.sleep(fwe.seconds + 1)
        except Exception as e:
            logger.warning("Error searching in chat %s: %s", chat_id, e)
            continue

    logger.info("Found %d total unique candidates for query '%s'", len(candidates), query)
    return candidates
