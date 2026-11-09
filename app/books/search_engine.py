import re
import difflib
import asyncio
from typing import List, Dict, Any, Optional
from app.database import get_db_connection
from app.books.classifier import classify_book_locally, normalize_amharic
from app.books.gemini_verifier import verify_books_batch_with_gemini
from app.config import logger, LOCAL_APPROVAL_THRESHOLD

# የተለመዱ የአማርኛ መስተዋድዶችና አያያዦች (Stopwords) - ነጥብ እንዳያዛቡ የሚወገዱ
AMHARIC_STOP_WORDS = {
    "እና", "ከ", "ወደ", "ስለ", "እስከ", "ላይ", "ውስጥ", "በ", "የ", "ወይም", "ነው", "ነበር", "ጋር", "ለ", "ዘ", "ወ"
}

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
        return 1.05

    # 2. Tier 2: የቃላት ሙሉ እኩልነት
    q_words = [w for w in query_norm.split() if w not in AMHARIC_STOP_WORDS and len(w) >= 2]
    c_words = set(c_norm.split())

    if not q_words:
        q_words = query_norm.split()

    q_set = set(q_words)
    if q_set and q_set == c_words:
        return 0.99

    # 3. Tier 3: ርዕሱ በጥያቄው የሚጀምር ከሆነ (Prefix Match)
    if c_norm.startswith(query_norm):
        len_ratio = len(query_norm) / max(len(c_norm), 1)
        return 0.85 + (len_ratio * 0.10)

    # 4. Tier 4: ጥያቄው በውስጡ ካለ (Substring Match)
    if query_norm in c_norm:
        len_ratio = len(query_norm) / max(len(c_norm), 1)
        return 0.72 + (len_ratio * 0.10)

    # 5. Tier 5: የዋና ቃላት ከፊል ተዛምዶ (Significant Word Overlap - Stopwords excluded)
    if q_set:
        overlap = q_set.intersection(c_words)
        if overlap:
            overlap_score = len(overlap) / len(q_set)
            # ቢያንስ 60% የሚሆኑት ዋና ቃላት ከተገኙ ብቻ ነጥብ ይሰጣል
            if overlap_score >= 0.6:
                return 0.55 + (overlap_score * 0.15)

    # 6. Tier 6: Levenshtein ratio
    ratio = difflib.SequenceMatcher(None, query_norm, c_norm).ratio()
    return ratio * 0.45

async def search_books_in_db(query: str, limit: int = 5, min_threshold: float = 0.50) -> List[Dict[str, Any]]:
    """በዳታቤዝ ውስጥ ያሉትን የተላኩ መጻሕፍት በተቀራራቢ ፍለጋ ይፈልጋል"""
    query_clean = query.strip()
    query_norm = normalize_amharic(query_clean)
    if not query_norm:
        return []

    results = []
    seen_ids = set()

    async with get_db_connection() as db:
        # 1. በቅድሚያ ንጹሕ ርዕሱን እና ፋይል ስሙን በ LIKE መፈለግ
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
                        "match_type": "exact_like"
                    })

        # 2. Approximate fallback
        if len(results) < limit:
            async with db.execute("""
                SELECT id, clean_title, requested_title, author, source, telegram_chat_id, telegram_message_id, filename, file_size 
                FROM processed_files 
                WHERE status = 'sent'
                LIMIT 300
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

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]

async def filter_and_rank_candidates(
    raw_candidates: List[Dict[str, Any]],
    query: str,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Fast Hybrid Filtering on Telegram Search candidates:
    1. Runs classify_book_locally in milliseconds (blocks Fiction/Secular/Academic immediately).
    2. Approves score >= 80 instantly (0 Gemini calls).
    3. Batches ambiguous candidates (20 <= score < 80) into a single Gemini batch call (1-2s total).
    """
    if not raw_candidates:
        return []

    query_norm = normalize_amharic(query)
    approved_candidates = []
    ambiguous_candidates = []

    for cand in raw_candidates:
        fn = cand.get("filename", "")
        cap = cand.get("caption", "")
        ch_title = cand.get("source_channel_title") or cand.get("chat_name", "")

        # 1. Local classification
        local = classify_book_locally(
            title=cand.get("title", ""),
            filename=fn,
            caption=cap,
            source_channel_title=ch_title
        )

        # Immediate Reject
        if local["category"] in ("Fiction", "Scientific/Academic", "Other_Religion", "Secular"):
            continue

        sim_score = calculate_similarity(query_norm, fn + " " + cap, fn)
        cand["similarity_score"] = sim_score
        cand["local_score"] = local["score"]
        cand["book_category"] = local["category"]

        # Immediate High-Score Local Approval
        if local["is_orthodox"] and local["score"] >= LOCAL_APPROVAL_THRESHOLD:
            cand["verified_by"] = "local_rules"
            cand["verification_reason"] = local["reason"]
            cand["confidence"] = 1.0
            approved_candidates.append(cand)
        elif local["score"] >= 20.0:
            ambiguous_candidates.append(cand)

    # 2. Batch Gemini Helper for ambiguous candidates (up to 10 at once)
    if ambiguous_candidates and len(approved_candidates) < limit:
        batch_slice = ambiguous_candidates[:10]
        batch_verdicts = await verify_books_batch_with_gemini(batch_slice)
        for cand, verdict in zip(batch_slice, batch_verdicts):
            if verdict.get("is_orthodox", False):
                cand["verified_by"] = "gemini_helper"
                cand["verification_reason"] = verdict.get("reason", "")
                cand["confidence"] = verdict.get("confidence", 0.9)
                cand["book_category"] = "Orthodox"
                approved_candidates.append(cand)

    # Sort primarily by similarity to query, then by local score
    approved_candidates.sort(key=lambda x: (x.get("similarity_score", 0.0) * 0.6 + (x.get("local_score", 0.0) / 100.0) * 0.4), reverse=True)
    return approved_candidates[:limit]

async def search_books_global(client, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Executes True Global Telegram Search across channels and filters through the Fast Hybrid Engine.
    """
    from app.telegram.search import search_documents_globally
    raw_candidates = await search_documents_globally(query, limit=50)

    # Map message object for sender compatibility
    verified = await filter_and_rank_candidates(raw_candidates, query=query, limit=limit)

    results = []
    for cand in verified:
        # Fetch the actual message object from the channel if needed
        chat_id = cand["telegram_chat_id"]
        msg_id = cand["message_id"]
        msg_obj = None
        try:
            msg_obj = await client.get_messages(chat_id, ids=msg_id)
        except Exception:
            pass

        results.append({
            "msg_obj": msg_obj,
            "title": cand.get("title") or re.sub(r"\.(pdf|epub|djvu)$", "", cand["filename"], flags=re.IGNORECASE).replace("_", " ").strip(),
            "filename": cand["filename"],
            "source": cand.get("source_channel_title") or cand.get("chat_name", "Telegram Channel"),
            "category": cand.get("book_category", "Orthodox"),
            "file_size": cand.get("file_size", 0),
            "score": cand.get("similarity_score", 0.8),
            "verified_by": cand.get("verified_by", "local_rules"),
            "match_type": "global_telegram"
        })

    return results
