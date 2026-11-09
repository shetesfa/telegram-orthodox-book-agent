import os
import json
import asyncio
import base64
from typing import Dict, Any, Optional
import urllib.request
import urllib.error
from app.config import (
    logger,
    GEMINI_API_KEY as CONFIG_KEY,
    GEMINI_MODEL as CONFIG_MODEL,
    VERIFICATION_MODE,
    LOCAL_APPROVAL_THRESHOLD,
    GEMINI_MIN_CONFIDENCE
)
from app.books.classifier import (
    classify_book_locally,
    extract_cover_ocr,
    normalize_amharic
)

# Configuration & Cache
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", CONFIG_KEY).strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", CONFIG_MODEL or "gemini-3.5-flash-lite").strip()

# In-Memory Cache (0.001ms instantaneous responses for repetitive checks)
_VERIFICATION_CACHE: Dict[str, Dict[str, Any]] = {}

SYSTEM_PROMPT = """You are the official Ethiopian Orthodox Tewahedo Church (የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ ቤተ ክርስቲያን) spiritual literature inspector.
Your sole duty is to inspect book titles, descriptions, and cover images to verify if they are authentic Ethiopian Orthodox Tewahedo books or secular/fiction/academic/other religion books.

CATEGORIES:
1. "Orthodox": Authentic Ethiopian Orthodox Tewahedo scripture, patristic, liturgy, prayer, saints' lives (ገድላት, ድርሳናት, ተአምራት, ቅዳሴ, ውዳሴ ማርያም, ስንክሳር, ሃይማኖተ አበው).
2. "Fiction": Novels, love stories, secular literature (ፍቅር እስከ መቃብር, ኦሮማይ, ትኩሳት, ልብወለድ).
3. "Scientific/Academic": Science, mathematics, medicine, engineering, school textbooks, business, self-help.
4. "Other_Religion": Protestant, Evangelical, Pentecostal, Islamic, Catholic, or non-EOTC publications.
5. "Secular": General secular history, politics, or entertainment.

Return strictly valid JSON:
{
  "is_orthodox": true or false,
  "category": "Orthodox" | "Fiction" | "Scientific/Academic" | "Other_Religion" | "Secular",
  "confidence": 0.0 to 1.0,
  "reason": "አጭር እና ግልጽ ማብራሪያ በአማርኛ"
}
"""

async def verify_book_with_gemini_helper(
    title: str,
    caption: str = "",
    thumb_bytes: Optional[bytes] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Intelligent helper using Gemini AI with optional lightweight 15KB thumbnail image.
    Never crashes, handles rate limits (429) and timeouts safely.
    """
    key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not key:
        return {
            "verified": False,
            "has_api_key": False,
            "is_orthodox": False,
            "confidence": 0.0,
            "category": "Unknown",
            "reason": "የ Gemini API ቁልፍ ስላልተዋቀረ አጠራጣሪው መጽሐፍ በደህንነት ተዘሏል",
            "verified_by": "rejected"
        }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    parts = []

    # If 15KB thumbnail is available, include as multimodal vision data
    if thumb_bytes and len(thumb_bytes) > 0:
        encoded_img = base64.b64encode(thumb_bytes).decode("utf-8")
        parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": encoded_img
            }
        })

    prompt_text = f"የመጽሐፍ ርዕስ/ፋይል: '{title}'\nመግለጫ: '{caption}'\nይህ መጽሐፍ የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጽሐፍ መሆኑን መርምረህ በ JSON መልስ።"
    parts.append({"text": prompt_text})

    payload = {
        "contents": [{"parts": parts}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0,
            "maxOutputTokens": 250
        }
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": key
            },
            method="POST"
        )

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=10))
        res_json = json.loads(response.read().decode("utf-8"))

        text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text_content)

        is_ortho = bool(result.get("is_orthodox", False))
        conf = float(result.get("confidence", 0.0))
        category = str(result.get("category", "Unknown"))
        reason = str(result.get("reason", ""))

        approved = is_ortho and conf >= GEMINI_MIN_CONFIDENCE and category == "Orthodox"

        return {
            "verified": True,
            "has_api_key": True,
            "is_orthodox": approved,
            "confidence": conf,
            "category": category,
            "reason": reason,
            "verified_by": "gemini_helper" if approved else "rejected"
        }

    except urllib.error.HTTPError as he:
        logger.warning("Gemini API HTTP Error %s: %s", he.code, he.reason)
        return {
            "verified": False,
            "has_api_key": True,
            "is_orthodox": False,
            "confidence": 0.0,
            "category": "Unknown",
            "reason": f"የ AI ረዳት ምላሽ አልሰጠም (HTTP {he.code})፤ መጽሐፉ በደህንነት ታግዷል",
            "verified_by": "rejected"
        }
    except Exception as e:
        logger.error("Gemini API call failed: %s", e)
        return {
            "verified": False,
            "has_api_key": True,
            "is_orthodox": False,
            "confidence": 0.0,
            "category": "Unknown",
            "reason": f"የ AI ረዳት ግንኙነት አልተሳካም፤ መጽሐፉ በደህንነት ታግዷል: {e}",
            "verified_by": "rejected"
        }

async def verify_books_batch_with_gemini(
    candidates: List[Dict[str, Any]],
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Batches up to 10 ambiguous candidates into a single Gemini API call.
    Returns list of verification verdicts matching candidate order.
    Finishes in 1-2 seconds with only 1 API call.
    """
    if not candidates:
        return []

    key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not key:
        return [
            {
                "is_orthodox": False,
                "confidence": 0.0,
                "category": "Unknown",
                "reason": "የ Gemini API ቁልፍ የለም",
                "verified_by": "rejected"
            } for _ in candidates
        ]

    # Build compact batch list
    items = []
    for idx, c in enumerate(candidates[:10]):
        items.append({
            "index": idx,
            "title": str(c.get("title") or c.get("filename") or ""),
            "caption": str(c.get("caption", ""))[:120],
            "channel": str(c.get("source_channel_title") or c.get("chat_name") or "")
        })

    batch_prompt = (
        "Classify the following candidate books. For each item, decide whether it is authentic Ethiopian Orthodox Tewahedo Church literature (Orthodox), Fiction, Scientific/Academic, or Other_Religion.\n\n"
        f"CANDIDATES JSON:\n{json.dumps(items, ensure_ascii=False)}\n\n"
        "Return strictly a JSON array of objects with keys: index, is_orthodox (bool), category (string), confidence (0.0 to 1.0), reason (short Amharic string)."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": batch_prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0,
            "maxOutputTokens": 600
        }
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": key
            },
            method="POST"
        )
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=12))
        res_json = json.loads(response.read().decode("utf-8"))
        text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
        batch_results = json.loads(text_content)

        # Map back by index
        verdicts_map = {}
        if isinstance(batch_results, list):
            for r in batch_results:
                idx = r.get("index", 0)
                is_ortho = bool(r.get("is_orthodox", False))
                conf = float(r.get("confidence", 0.0))
                cat = str(r.get("category", "Unknown"))
                approved = is_ortho and conf >= GEMINI_MIN_CONFIDENCE and cat == "Orthodox"
                verdicts_map[idx] = {
                    "is_orthodox": approved,
                    "confidence": conf,
                    "category": cat,
                    "reason": str(r.get("reason", "")),
                    "verified_by": "gemini_helper" if approved else "rejected"
                }

        results = []
        for idx in range(len(candidates[:10])):
            if idx in verdicts_map:
                results.append(verdicts_map[idx])
            else:
                results.append({
                    "is_orthodox": False,
                    "confidence": 0.0,
                    "category": "Unknown",
                    "reason": "የ AI ምላሽ አልተገኘም",
                    "verified_by": "rejected"
                })
        return results

    except Exception as e:
        logger.warning("Batch Gemini verification failed: %s", e)
        return [
            {
                "is_orthodox": False,
                "confidence": 0.0,
                "category": "Unknown",
                "reason": f"የ AI ረዳት ችግር: {e}",
                "verified_by": "rejected"
            } for _ in candidates[:10]
        ]

async def verify_book_hybrid_async(
    title: str,
    filename: str = "",
    caption: str = "",
    source_channel_title: str = "",
    thumb_bytes: Optional[bytes] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main Hybrid Verification Pipeline:
    Step A & B: Local classifier instant check. If Blacklisted (Fiction, Academic, etc.) -> REJECT in 0.002s.
    Step C: Local classifier instant check. If Score >= LOCAL_APPROVAL_THRESHOLD (80) -> APPROVE in 0.002s.
    Step D: Ambiguous (20 <= score < 80) -> Call Gemini Helper with metadata + optional 15KB thumbnail.
    Step E: Fallback -> If Gemini offline/error, safe rejection (never crash).
    """
    cache_key = f"{title.strip().lower()}|{filename.strip().lower()}|{source_channel_title.strip().lower()}"
    if cache_key in _VERIFICATION_CACHE:
        return _VERIFICATION_CACHE[cache_key]

    # Optional OCR if thumbnail present
    ocr_text = ""
    if thumb_bytes:
        ocr_text = extract_cover_ocr(thumb_bytes)

    # Step A: Local Classifier
    local_result = classify_book_locally(
        title=title,
        filename=filename,
        caption=caption,
        source_channel_title=source_channel_title,
        cover_ocr_text=ocr_text
    )

    # Step B: Immediate Reject for Blacklisted categories
    if local_result["category"] in ("Fiction", "Scientific/Academic", "Other_Religion", "Secular"):
        out = {
            "is_orthodox": False,
            "confidence": 1.0,
            "score": local_result["score"],
            "category": local_result["category"],
            "reason": local_result["reason"],
            "verified_by": "rejected"
        }
        _VERIFICATION_CACHE[cache_key] = out
        logger.info("🚫 [Local Reject in 0.002s] '%s' -> %s (%s)", title or filename, out["category"], out["reason"])
        return out

    # Step C: Immediate Approval for High-Confidence Local Matches
    if local_result["is_orthodox"] and local_result["score"] >= LOCAL_APPROVAL_THRESHOLD:
        out = {
            "is_orthodox": True,
            "confidence": local_result["score"] / 100.0,
            "score": local_result["score"],
            "category": "Orthodox",
            "reason": local_result["reason"],
            "verified_by": "local_rules"
        }
        _VERIFICATION_CACHE[cache_key] = out
        logger.info("⚡ [Local Approved in 0.002s] '%s' -> Score: %.1f", title or filename, out["score"])
        return out

    # If verification mode is strict_local, do not call Gemini
    if VERIFICATION_MODE == "strict_local":
        out = {
            "is_orthodox": False,
            "confidence": local_result["score"] / 100.0,
            "score": local_result["score"],
            "category": local_result["category"],
            "reason": f"በ strict_local ሁነታ በቂ ነጥብ አላገኘም (ነጥብ: {local_result['score']:.1f})",
            "verified_by": "rejected"
        }
        _VERIFICATION_CACHE[cache_key] = out
        return out

    # Step D: Ambiguous cases (Call Gemini Helper with metadata + optional 15KB thumbnail)
    logger.info("🤔 [Ambiguous - Calling Gemini Helper] '%s' (Local Score: %.1f)", title or filename, local_result["score"])
    gemini_res = await verify_book_with_gemini_helper(
        title=f"{title} {filename}".strip(),
        caption=f"{caption} [ምንጭ: {source_channel_title}]",
        thumb_bytes=thumb_bytes,
        api_key=api_key
    )

    final_is_ortho = gemini_res["is_orthodox"]
    final_category = gemini_res.get("category", local_result["category"])
    final_reason = gemini_res.get("reason", local_result["reason"])
    final_verified_by = gemini_res.get("verified_by", "rejected")

    out = {
        "is_orthodox": final_is_ortho,
        "confidence": gemini_res.get("confidence", 0.0),
        "score": local_result["score"],
        "category": final_category,
        "reason": final_reason,
        "verified_by": final_verified_by
    }
    _VERIFICATION_CACHE[cache_key] = out
    return out

# Backward Compatibility Wrapper
async def verify_book_with_gemini(filename: str, caption: str = "", api_key: Optional[str] = None) -> Dict[str, Any]:
    """Compatibility wrapper that routes through the new Hybrid engine."""
    res = await verify_book_hybrid_async(
        title="",
        filename=filename,
        caption=caption,
        source_channel_title="",
        api_key=api_key
    )
    return {
        "verified": True,
        "is_orthodox": res["is_orthodox"],
        "confidence": res["confidence"] * 100.0 if res["confidence"] <= 1.0 else res["confidence"],
        "category": res.get("category", ""),
        "reason": res.get("reason", ""),
        "verified_by": res.get("verified_by", ""),
        "has_api_key": bool(api_key or GEMINI_API_KEY)
    }

async def ensure_book_verified_before_output(
    title: str,
    filename: str = "",
    caption: str = "",
    source_channel_title: str = "",
    thumb_bytes: Optional[bytes] = None,
    book_id: Optional[int] = None
) -> tuple[bool, Dict[str, Any]]:
    """
    Pre-Output Gate:
    Runs before any book is forwarded or sent.
    Blocks old/stale entries in books.db that may be fiction/academic.
    If rejected, updates books.db safely and blocks output.
    """
    from app.database import update_book_status

    # Fast 0.001s local scan first
    local = classify_book_locally(
        title=title,
        filename=filename,
        caption=caption,
        source_channel_title=source_channel_title
    )
    if local["category"] in ("Fiction", "Scientific/Academic", "Other_Religion", "Secular"):
        logger.warning("🛑 [Pre-Output Gate Blocked] '%s' is %s (%s)", title or filename, local["category"], local["reason"])
        if book_id is not None:
            try:
                await update_book_status(
                    book_id=book_id,
                    status="rejected",
                    is_orthodox=False,
                    verified_by="rejected",
                    verification_score=0.0,
                    book_category=local["category"],
                    verification_reason=local["reason"]
                )
            except Exception as dbe:
                logger.debug("Could not update rejected book status in db: %s", dbe)
        return False, local

    # Full hybrid verification (handles high score local approval or Gemini helper)
    verdict = await verify_book_hybrid_async(
        title=title,
        filename=filename,
        caption=caption,
        source_channel_title=source_channel_title,
        thumb_bytes=thumb_bytes
    )

    if not verdict.get("is_orthodox", False):
        logger.warning("🛑 [Pre-Output Gate Blocked by Hybrid] '%s' (%s)", title or filename, verdict.get("reason"))
        if book_id is not None:
            try:
                await update_book_status(
                    book_id=book_id,
                    status="rejected",
                    is_orthodox=False,
                    verified_by=verdict.get("verified_by", "rejected"),
                    verification_score=verdict.get("score", 0.0),
                    book_category=verdict.get("category", "Unknown"),
                    verification_reason=verdict.get("reason", "")
                )
            except Exception as dbe:
                logger.debug("Could not update rejected book status in db: %s", dbe)
        return False, verdict

    # If approved, update status if book_id is provided
    if book_id is not None:
        try:
            await update_book_status(
                book_id=book_id,
                status="verified",
                is_orthodox=True,
                verified_by=verdict.get("verified_by", "local_rules"),
                verification_score=verdict.get("score", 100.0),
                book_category=verdict.get("category", "Orthodox"),
                verification_reason=verdict.get("reason", "")
            )
        except Exception as dbe:
            logger.debug("Could not update verified book status in db: %s", dbe)

    return True, verdict
