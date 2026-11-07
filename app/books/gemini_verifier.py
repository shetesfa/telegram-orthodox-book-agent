import os
import json
import asyncio
from typing import Dict, Any, Optional
import urllib.request
import urllib.error
from app.config import logger, GEMINI_API_KEY as CONFIG_KEY, GEMINI_MODEL as CONFIG_MODEL

# ነጻ እና እጅግ ፈጣን የ Gemini ሞዴል ውቅር
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", CONFIG_KEY).strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", CONFIG_MODEL or "gemini-3.5-flash-lite").strip()

# እጅግ ፈጣን የውስጥ ማከማቻ (In-Memory Cache) - አንድ መጽሐፍ በድጋሚ ሲፈተሽ በ 0.001ms ይመልሳል
_VERIFICATION_CACHE: Dict[str, Dict[str, Any]] = {}

SYSTEM_PROMPT = """You are the official Ethiopian Orthodox Tewahedo Church (የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ ቤተክርስቲያን) spiritual document and literature verifier.
Your absolute mission is to guarantee that only 100% genuine Ethiopian Orthodox Tewahedo Church holy books, teachings, liturgies, and patristic texts are permitted.

APPROVED ORTHODOX CATEGORIES:
1. Holy Bible (ብሉያት እና ሐዲሳት, የ 81ዱ መጻሕፍት አንድምታ ትርጓሜያት)
2. Hagiographies & Homilies (ገድላት, ድርሳናት, ተአምራት, ዜና ቅዱሳን)
3. Liturgical, Chant & Choirs (ቅዳሴ, ድጓ, ጾመ ድጓ, ዝማሬ, መዋሥዕት, ምዕራፍ, ማኅሌተ ጽጌ, ሰዓታት)
4. Prayers & Praises (ውዳሴ ማርያም, መዝሙረ ዳዊት, ሰይፈ ሥላሴ, አርጋኖን, መልክአ ቅዱሳን, መጽሐፈ ሰዓታት)
5. Patristic Theology & Canon (ሃይማኖተ አበው, ፍትሐ ነገሥት, መጽሐፈ ምስጢር, ስንክሳር, ባሕረ ሐሳብ, አቡሻክር, ዲድስቅልያ, ኪዳን)
6. Monastic Wisdom (አረጋዊ መንፈሳዊ, ማር ይስሐቅ, ፊልክስዩስ, ዜና አበው)
7. Ecclesiastical Ge'ez Language (የግእዝ ሰዋስው, መዝገበ ቃላት, ጥንታዊ የብራና ጽሑፎች)

STRICTLY FORBIDDEN & REJECTED:
1. Secular fictions, novels, romance, crime, drama, love stories (e.g. ፍቅር እስከ መቃብር, ትኩሳት, ሌቱም አይነጋልኝ, ወንጀል እና ቅጣት, አለመኖር, fiction, novel)
2. School & Academic textbooks (e.g. ሒሳብ, ፊዚክስ, ኬሚስትሪ, ባዮሎጂ, ሳይንስ, Grade 1-12, exam, matric, fetena, student textbook)
3. Non-Orthodox religious books (Protestant, Pentecostal, Catholic, Islamic, Jehovah's Witnesses, P'ente)
4. Secular politics, gossip, mundane history, sports, entertainment

You MUST respond strictly in valid JSON format:
{
  "is_orthodox": true or false,
  "confidence": 0 to 100,
  "reason": "አጭር እና ግልጽ ማብራሪያ በአማርኛ"
}
"""

async def verify_book_with_gemini(filename: str, caption: str = "", api_key: Optional[str] = None) -> Dict[str, Any]:
    """Gemini 3.5 Flash Lite ኤፒአይን በመጠቀም መጽሐፉን በቅጽበት መርምሮ ያረጋግጣል"""
    # 1. ርዕሱን ከስም አጽዳ
    cache_key = f"{filename.strip().lower()}|{caption.strip()[:100].lower()}"
    if cache_key in _VERIFICATION_CACHE:
        cached = _VERIFICATION_CACHE[cache_key]
        logger.info("⚡ [Gemini Cache Hit] '%s' -> is_orthodox=%s", filename, cached.get("is_orthodox"))
        return cached

    key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not key:
        logger.warning("Gemini API key is not configured.")
        return {
            "verified": False,
            "has_api_key": False,
            "is_orthodox": False,
            "reason": "የ Gemini API Key አልተዋቀረም"
        }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    prompt_text = f"የመጽሐፉ ፋይል ስም/ርዕስ: '{filename}'\nመግለጫ (Caption): '{caption}'\nይህ መጽሐፍ የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጽሐፍ መሆኑን ብቻ አረጋግጥ።"

    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }],
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0,
            "maxOutputTokens": 200
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
        result = json.loads(text_content)
        
        is_ortho = bool(result.get("is_orthodox", False))
        conf = float(result.get("confidence", 0))
        reason = str(result.get("reason", ""))

        out = {
            "verified": True,
            "is_orthodox": is_ortho and conf >= 70.0,
            "confidence": conf,
            "reason": reason,
            "has_api_key": True
        }
        
        # ካሽ ውስጥ አስቀምጥ
        _VERIFICATION_CACHE[cache_key] = out
        logger.info("🤖 [Gemini Verified] '%s': is_orthodox=%s (conf=%.1f%%, ምክንያት: %s)", filename, out["is_orthodox"], conf, reason)
        return out

    except Exception as e:
        logger.error("Gemini verification call failed for '%s': %s", filename, e)
        return {
            "verified": False,
            "has_api_key": True,
            "is_orthodox": False,
            "error": str(e),
            "reason": f"የ AI ፍተሻ ስህተት አጋጥሟል: {e}"
        }
