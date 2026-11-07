import re
import difflib
from typing import List, Dict, Any, Optional
from app.database import get_db_connection
from app.telegram.harvester import is_orthodox_book, is_definitely_fiction_or_secular, classify_orthodox_book
from app.config import logger

# የአማርኛ የሆሞፎን ፊደላት መተኪያ ሰንጠረዥ (Homophone Normalization Table)
AMHARIC_HOMOPHONE_MAP = {
    # ሐ, ኀ -> ሀ
    'ሐ': 'ሀ', 'ሑ': 'ሁ', 'ሒ': 'ሂ', 'ሓ': 'ሃ', 'ሔ': 'ሄ', 'ሕ': 'ህ', 'ሖ': 'ሆ',
    'ኀ': 'ሀ', 'ኁ': 'ሁ', 'ኂ': 'ሂ', 'ኃ': 'ሃ', 'ኄ': 'ሄ', 'ኅ': 'ህ', 'ኆ': 'ሆ',
    # ሠ -> ሰ
    'ሠ': 'ሰ', 'ሡ': 'ሱ', 'ሢ': 'ሲ', 'ሣ': 'ሳ', 'ሤ': 'ሴ', 'ሥ': 'ስ', 'ሦ': 'ሶ',
    # ዐ -> አ
    'ዐ': 'አ', 'ዑ': 'ኡ', 'ዒ': 'ኢ', 'ዓ': 'አ', 'ዔ': 'ኤ', 'ዕ': 'እ', 'ዖ': 'ኦ',
    # ፀ -> ጸ
    'ፀ': 'ጸ', 'ፁ': 'ጹ', 'ፂ': 'ጺ', 'ፃ': 'ጻ', 'ፄ': 'ጼ', 'ፅ': 'ጽ', 'ፆ': 'ጾ',
}

def normalize_amharic(text: str) -> str:
    """የአማርኛ ጽሑፍን ፊደላት፣ ክፍተቶችና ምልክቶች ወደ አንድ ወጥ ቅርጽ ይቀይራል"""
    if not text:
        return ""
    text = text.lower()
    for char, replacement in AMHARIC_HOMOPHONE_MAP.items():
        text = text.replace(char, replacement)
    # ልዩ ምልክቶችንና underscoreን ወደ ክፍተት መቀየር
    text = re.sub(r'[\.\_\-\:\(\)\[\]\\\/]+', ' ', text)
    # ከመጠን በላይ የሆኑ ክፍተቶችን ማጽዳት
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def calculate_similarity(query_norm: str, clean_title: str, raw_filename: str = "") -> float:
    """ፍጹም ጥብቅ እና አስተማማኝ የነጥብ አሰጣጥ ስርዓት (Bulletproof Hierarchy)"""
    if not query_norm:
        return 0.0

    c_norm = normalize_amharic(clean_title or "")
    if not c_norm:
        c_norm = normalize_amharic(raw_filename or "")
        c_norm = re.sub(r'\.(pdf|epub|djvu)$', '', c_norm).strip()

    # 1. Tier 1: ፍጹም እኩል (100% Exact Match)
    if query_norm == c_norm:
        # ንጹሕ የፋይል ስም ያለው ቅድሚያ እንዲያገኝ ትንሽ ቦነስ ይሰጠዋል
        cleanliness_bonus = 0.05 if not re.search(r'[@\(\)0-9]', raw_filename) else 0.01
        return 1.0 + cleanliness_bonus

    # 2. Tier 2: የቃላት ሙሉ እኩልነት
    q_words = set(query_norm.split())
    c_words = set(c_norm.split())
    if q_words and q_words == c_words:
        return 0.99

    # 3. Tier 3: ርዕሱ በጥያቄው የሚጀምር ከሆነ (Prefix Match)
    if c_norm.startswith(query_norm):
        len_ratio = len(query_norm) / max(len(c_norm), 1)
        return 0.85 + (len_ratio * 0.10)

    # 4. Tier 4: ጥያቄው በውስጡ ካለ (Substring Match)
    if query_norm in c_norm:
        len_ratio = len(query_norm) / max(len(c_norm), 1)
        return 0.72 + (len_ratio * 0.10)

    # 5. Tier 5: የቃላት ከፊል ተዛምዶ (Word Overlap)
    overlap = q_words.intersection(c_words)
    if overlap:
        overlap_score = len(overlap) / len(q_words)
        if overlap_score >= 0.5:
            return 0.55 + (overlap_score * 0.15)

    # 6. Tier 6: Levenshtein
    return difflib.SequenceMatcher(None, query_norm, c_norm).ratio() * 0.50

async def search_books_in_db(query: str, limit: int = 5, min_threshold: float = 0.45) -> List[Dict[str, Any]]:
    """በዳታቤዝ ውስጥ ያሉትን የተላኩ መጻሕፍት በተቀራራቢ ፍለጋ (Approximate Match) ይፈልጋል"""
    query_clean = query.strip()
    query_norm = normalize_amharic(query_clean)
    if not query_norm:
        return []

    results = []
    seen_ids = set()

    async with get_db_connection() as db:
        # 1. በቅድሚያ ንጹሕ ርዕሱን (clean_title) እና ፋይል ስሙን በ LIKE መፈለግ
        like_term = f"%{query_clean}%"
        async with db.execute("""
            SELECT id, clean_title, requested_title, author, source, telegram_chat_id, telegram_message_id, filename, file_size 
            FROM processed_files 
            WHERE status = 'sent' AND (clean_title LIKE ? OR requested_title LIKE ? OR filename LIKE ?)
            LIMIT 50
        """, (like_term, like_term, like_term)) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                seen_ids.add(row["id"])
                c_title = row["clean_title"] or row["requested_title"] or row["filename"]
                score = calculate_similarity(query_norm, c_title, row["filename"])
                results.append({
                    "id": row["id"],
                    "title": c_title,
                    "clean_title": c_title,
                    "filename": row["filename"],
                    "source": row["source"],
                    "telegram_chat_id": row["telegram_chat_id"],
                    "telegram_message_id": row["telegram_message_id"],
                    "file_size": row["file_size"],
                    "score": score,
                    "match_type": "exact_or_substring"
                })

        # 2. በቂ ካልተገኘ ሙሉውን ዳታቤዝ በሆሞፎን ኖርማላይዜሽን መፈተሽ
        if len(results) < limit:
            async with db.execute("""
                SELECT id, clean_title, requested_title, author, source, telegram_chat_id, telegram_message_id, filename, file_size 
                FROM processed_files 
                WHERE status = 'sent'
            """) as cursor:
                async for row in cursor:
                    if row["id"] in seen_ids:
                        continue
                    c_title = row["clean_title"] or row["requested_title"] or row["filename"]
                    score = calculate_similarity(query_norm, c_title, row["filename"])
                    if score >= min_threshold:
                        results.append({
                            "id": row["id"],
                            "title": c_title,
                            "clean_title": c_title,
                            "filename": row["filename"],
                            "source": row["source"],
                            "telegram_chat_id": row["telegram_chat_id"],
                            "telegram_message_id": row["telegram_message_id"],
                            "file_size": row["file_size"],
                            "score": score,
                            "match_type": "approximate"
                        })

    # በከፍተኛ ውጤት ነጥብ ቅደም ተከተል ማደራጀት
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]

async def search_books_global(client, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """በዳታቤዝ ውስጥ ላልተገኙ መጻሕፍት በቴሌግራም ግሎባል ክላውድ ፈልጎ ያረጋግጣል"""
    from telethon.tl.types import InputMessagesFilterDocument, DocumentAttributeFilename
    
    query_clean = query.strip()
    query_norm = normalize_amharic(query_clean)
    if not client or not client.is_connected() or not query_norm:
        return []

    global_matches = []
    seen_files = set()

    try:
        logger.info("Executing Global Fallback Telegram Search for '%s'...", query_clean)
        async for msg in client.iter_messages(None, search=query_clean, filter=InputMessagesFilterDocument, limit=40):
            if not msg.document:
                continue

            filename = ""
            for attr in msg.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break
            if not filename:
                ext = msg.file.ext or ".pdf"
                filename = f"book_{msg.id}{ext}"

            if filename in seen_files:
                continue
            seen_files.add(filename)

            caption = msg.text or ""
            # የይዘት ጥበቃ እና ማጣራት
            if is_definitely_fiction_or_secular(filename, caption):
                continue
            if not is_orthodox_book(filename, caption):
                continue

            t_norm = normalize_amharic(filename + " " + caption)
            score = calculate_similarity(query_norm, t_norm)
            if score < 0.35:
                continue

            chat_title = "Global Orthodox Library"
            try:
                chat = await msg.get_chat()
                chat_title = getattr(chat, "title", "Global Channel")
            except Exception:
                pass

            clean_title = re.sub(r"\.(pdf|epub|djvu)$", "", filename, flags=re.IGNORECASE).replace("_", " ").strip()
            cat = classify_orthodox_book(filename, caption)

            global_matches.append({
                "msg_obj": msg,
                "title": clean_title,
                "filename": filename,
                "source": chat_title,
                "category": cat,
                "file_size": msg.document.size or 0,
                "score": score,
                "match_type": "global_telegram"
            })

            if len(global_matches) >= limit:
                break

    except Exception as ge:
        logger.error("Error during global book search: %s", ge)

    global_matches.sort(key=lambda x: x["score"], reverse=True)
    return global_matches[:limit]
