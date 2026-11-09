import re
import io
from typing import Dict, Any, Optional, Tuple, List
from app.config import logger, LOCAL_APPROVAL_THRESHOLD

def normalize_amharic(text: str) -> str:
    """
    Normalizes Amharic homophones, removes punctuation/separators,
    and strips extra whitespace for robust classification and matching.
    """
    if not text:
        return ""
    
    text = text.lower()

    # File extensions removal
    text = re.sub(r"\.(pdf|epub|mobi|djvu|docx?|txt)$", "", text, flags=re.IGNORECASE)

    # Homophone replacements
    replacements = {
        # ሐ, ኀ -> ሀ
        'ሐ': 'ሀ', 'ሑ': 'ሁ', 'ሒ': 'ሂ', 'ሓ': 'ሃ', 'ሔ': 'ሄ', 'ሕ': 'ህ', 'ሖ': 'ሆ',
        'ኀ': 'ሀ', 'ኁ': 'ሁ', 'ኂ': 'ሂ', 'ኃ': 'ሃ', 'ኄ': 'ሄ', 'ኅ': 'ህ', 'ኆ': 'ሆ',
        # ሠ -> ሰ
        'ሠ': 'ሰ', 'ሡ': 'ሱ', 'ሢ': 'ሲ', 'ሣ': 'ሳ', 'ሴ': 'ሴ', 'ሥ': 'ስ', 'ሦ': 'ሶ',
        # ዐ -> አ
        'ዐ': 'አ', 'ዑ': 'ኡ', 'ዒ': 'ኢ', 'ዓ': 'አ', 'ዔ': 'ኤ', 'ዕ': 'እ', 'ዖ': 'ኦ',
        # ፀ -> ጸ
        'ፀ': 'ጸ', 'ፁ': 'ጹ', 'ፂ': 'ጺ', 'ፃ': 'ጻ', 'ፄ': 'ጼ', 'ፅ': 'ጽ', 'ፆ': 'ጾ',
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)

    # Replace separators and punctuation with spaces
    text = re.sub(r"[_\-\.\+\[\]\(\)\{\},:፤፡፦!?'\"`~@#$%^&*\/\\|<>]+", " ", text)
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    return text

# Category 1 — STRICT REJECT (Fiction / Literature)
FICTION_MARKERS = [
    "ልብ ወለድ", "ልቦለድ", "አጭር ልብ ወለድ", "ረጅም ልብ ወለድ", "ፍቅር እስከ መቃብር",
    "ኦሮማይ", "እቴሜቴ", "ዣንቶዣራ", "ትኩሳት", "ሰመመን", "ያልተከፈለ ዕዳ",
    "ግራጫ ቃጭሎች", "ዝጎራ", "ራማቶሓራ", "ዮቶር", "ሜሎስ", "novel", "fiction",
    "romance", "thriller", "sci-fi", "drama", "short stories",
    "goodamharicbooks", "kooblife", "amharic novel"
]

# Category 2 — STRICT REJECT (Scientific / Academic / Textbooks / Self-Help / Secular)
SCIENTIFIC_SECULAR_MARKERS = [
    "physics", "chemistry", "biology", "mathematics", "calculus", "algebra",
    "geometry", "statistics", "engineering", "computer science", "programming",
    "python", "javascript", "medicine", "anatomy", "pharmacology", "economics",
    "accounting", "management", "marketing", "psychology", "sociology",
    "philosophy", "grade 9", "grade 10", "grade 11", "grade 12", "freshman",
    "module", "textbook", "exam", "worksheet", "curriculum", "self-help",
    "rich dad", "think and grow rich", "atomic habits", "48 laws", "ሳይንስ",
    "ፊዚክስ", "ኬሚስትሪ", "ባዮሎጂ", "ሒሳብ", "ሥነ ልቦና", "ኢኮኖሚክስ", "ቢዝነስ",
    "ፖለቲካ", "ዲሞክራሲ", "ምርጫ"
]

# Category 3 — STRICT REJECT (Non-Orthodox Religious)
OTHER_RELIGION_MARKERS = [
    "protestant", "pente", "evangelical", "pentecostal", "jehovah",
    "watchtower", "quran", "islam", "muslim", "hadith", "tafsir",
    "buddhism", "hindu", "new age", "ፓስተር", "ነቢይ", "ሐዋርያው",
    "ፕሮቴስታንት", "ጴንጤ", "ቁርአን", "እስልምና", "ሙስሊም"
]

# Unmistakable EOTC Canonical/Liturgical Titles (+60 points)
EOTC_CANONICAL_TITLES = [
    "ስንክሳር", "ሃይማኖተ አበው", "ፍትሐ ነገሥት", "መጽሐፈ ቅዳሴ", "ውዳሴ ማርያም",
    "መጽሐፈ ሰዓታት", "ተአምረ ማርያም", "ተአምረ ኢየሱስ", "ጾመ ድጓ", "መዝገበ ጸሎት",
    "ሰይፈ ሥላሴ", "አርጋኖን", "ዓምደ ሃይማኖት", "ነገረ ማርያም"
]

# Category 4 — STRONG EOTC POSITIVE SCORING (Core Books/Liturgy)
EOTC_CORE_MARKERS = [
    "ስንክሳር", "ሃይማኖተ አበው", "ፍትሐ ነገሥት", "መጽሐፈ ቅዳሴ", "ውዳሴ ማርያም",
    "አንድምታ", "ትርጓሜ", "ድጓ", "ጾመ ድጓ", "ዝማሬ", "መዋሥዕት", "መጽሐፈ ሰዓታት",
    "ተአምረ ማርያም", "ተአምረ ኢየሱስ", "ገድለ", "ድርሳነ", "መልክአ", "መዝገበ ጸሎት",
    "ሰይፈ ሥላሴ", "አርጋኖን", "መጽሐፈ ምሥጢር", "ዓምደ ሃይማኖት", "ነገረ ማርያም",
    "ነገረ ቅዱሳን", "ነገረ ክርስቶስ", "ምሥጢራተ ቤተ ክርስቲያን", "ሥርዓተ ቤተ ክርስቲያን",
    "ማኅሌት", "ሥርዓተ ማኅሌት", "ማኅሌተ ጽጌ"
]

# Category 4 — STRONG EOTC POSITIVE SCORING (+35 points for Identity/Titles/Patristics)
EOTC_IDENTITY_MARKERS = [
    "ኦርቶዶክስ", "ተዋሕዶ", "የኢትዮጵያ ኦርቶዶክስ", "ቤተ ክርስቲያን", "ቅዱስ ያሬድ",
    "አባ ጊዮርጊስ ዘጋሥጫ", "ቅዱስ ዮሐንስ አፈወርቅ", "ቅዱስ ቄርሎስ", "ቅዱስ አትናቴዎስ",
    "ቅዱስ ባስልዮስ", "ቅዱስ ጎርጎርዮስ", "ቅዱስ ኤፍሬም", "አቡነ ሺኖዳ", "ብፁዕ አቡነ",
    "ሊቀ ጳጳስ", "ፓትርያርክ", "ማኅበረ ቅዱሳን", "ዲያቆን", "ቀሲስ", "መልአከ",
    "ሊቀ ሊቃውንት", "መጋቤ ብሉይ", "መጋቤ ሐዲስ", "ቆሞስ", "monk",
    "ethiopian orthodox", "tewahedo", "eotc"
]

# Channel positive markers (+25 points)
EOTC_CHANNEL_MARKERS = [
    "ኦርቶዶክስ", "ተዋሕዶ", "ማኅበረ ቅዱሳን", "orthodox", "tewahedo"
]

def extract_cover_ocr(thumb_bytes: bytes) -> str:
    """
    Lightweight OCR extraction from ~15KB thumbnail image using pytesseract.
    Returns empty string safely if pytesseract or tesseract binary is not installed.
    """
    if not thumb_bytes:
        return ""
    try:
        from PIL import Image
        import pytesseract
        image = Image.open(io.BytesIO(thumb_bytes))
        # Try both Amharic and English if available
        try:
            text = pytesseract.image_to_string(image, lang="amh+eng")
        except Exception:
            text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        logger.debug("OCR extraction skipped or unavailable: %s", e)
        return ""

def classify_book_locally(
    title: str = "",
    filename: str = "",
    caption: str = "",
    source_channel_title: str = "",
    cover_ocr_text: str = ""
) -> Dict[str, Any]:
    """
    Fast, independent local text classifier.
    Returns:
      {
        "is_orthodox": bool,
        "score": float (0-100),
        "category": str ('Orthodox', 'Fiction', 'Scientific/Academic', 'Other_Religion', 'Secular', 'Unknown'),
        "reason": str,
        "verified_by": 'local_rules' or 'rejected' or 'pending_helper'
      }
    """
    raw_combined = f"{title} {filename} {caption} {cover_ocr_text}"
    norm_text = normalize_amharic(raw_combined)
    norm_channel = normalize_amharic(source_channel_title)

    # 1. Category 1: STRICT REJECT (Fiction / Literature)
    for marker in FICTION_MARKERS:
        norm_marker = normalize_amharic(marker)
        if norm_marker and norm_marker in norm_text:
            return {
                "is_orthodox": False,
                "score": 0.0,
                "category": "Fiction",
                "reason": f"የልብ ወለድ/ሥነ ጽሑፍ ምልክት ተገኝቷል: «{marker}»",
                "verified_by": "rejected"
            }

    # 2. Category 2: STRICT REJECT (Scientific / Academic / Textbooks / Secular)
    for marker in SCIENTIFIC_SECULAR_MARKERS:
        norm_marker = normalize_amharic(marker)
        # Use word boundaries for short English academic tokens like 'exam' or 'module'
        if marker.isascii() and marker.isalpha() and len(marker) <= 6:
            if re.search(r'\b' + re.escape(marker) + r'\b', raw_combined, flags=re.IGNORECASE):
                return {
                    "is_orthodox": False,
                    "score": 0.0,
                    "category": "Scientific/Academic",
                    "reason": f"የትምህርት/የሳይንስ ወይም ዓለማዊ መጽሐፍ ምልክት ተገኝቷል: «{marker}»",
                    "verified_by": "rejected"
                }
            continue

        if norm_marker and (norm_marker in norm_text or norm_marker in raw_combined.lower()):
            # Exception: Church history terms like "ፓትርያርክ" shouldn't be blocked by "ምርጫ"
            if norm_marker in ("ምርጫ", "ፖለቲካ") and any(h in norm_text for h in ["ፓትርያርክ", "ቤተ ክርስቲያን", "ጳጳስ", "ተዋህዶ", "ኦርቶዶክስ"]):
                continue

            return {
                "is_orthodox": False,
                "score": 0.0,
                "category": "Scientific/Academic",
                "reason": f"የትምህርት/የሳይንስ ወይም ዓለማዊ መጽሐፍ ምልክት ተገኝቷል: «{marker}»",
                "verified_by": "rejected"
            }

    # 3. Category 3: STRICT REJECT (Non-Orthodox Religious)
    for marker in OTHER_RELIGION_MARKERS:
        norm_marker = normalize_amharic(marker)
        if norm_marker and norm_marker in norm_text:
            # Exception: Biblical prophets/apostles revered in EOTC liturgy (e.g., ኤልሳዕ ነቢይ, ነቢዩ ዳዊት, ቅዱስ ጳውሎስ ሐዋርያው)
            eotc_holy_terms = ["ኤልሳእ", "ዳዊት", "ሙሴ", "ማህሌት", "ማኅሌት", "ስርዓተ", "ሥርዓተ", "ቅዳሴ", "ቅዱስ", "ገድለ", "ድርሳነ", "መልክአ", "ተዋህዶ", "ኦርቶዶክስ"]
            if norm_marker in ("ነቢይ", "ሐዋርያው") and any(normalize_amharic(h) in norm_text for h in eotc_holy_terms):
                continue

            return {
                "is_orthodox": False,
                "score": 0.0,
                "category": "Other_Religion",
                "reason": f"ከኦርቶዶክስ ተዋሕዶ ውጭ የሆነ የሌላ እምነት ምልክት ተገኝቷል: «{marker}»",
                "verified_by": "rejected"
            }

    # 4. Category 4: POSITIVE EOTC SCORING (0 to 100 points)
    score = 0.0
    matched_reasons = []

    # Unmistakable Canonical/Liturgical Titles (+60 points)
    canonical_hit = False
    matched_canonical = None
    for marker in EOTC_CANONICAL_TITLES:
        norm_marker = normalize_amharic(marker)
        if norm_marker and norm_marker in norm_text:
            score += 60.0
            matched_canonical = norm_marker
            matched_reasons.append(f"ቀኖናዊ/ሥርዓተ አምልኮ የቤተክርስቲያን መጽሐፍ («{marker}»)")
            canonical_hit = True
            break  # Apply +60 once

    # Core EOTC books/liturgy (+25 if canonical already matched, else +45)
    core_hit = False
    for marker in EOTC_CORE_MARKERS:
        norm_marker = normalize_amharic(marker)
        if norm_marker and norm_marker in norm_text:
            if canonical_hit and norm_marker == matched_canonical:
                continue  # Avoid double scoring the exact same token
            pts = 25.0 if canonical_hit else 45.0
            score += pts
            matched_reasons.append(f"መሰረታዊ የቤተክርስቲያን መጽሐፍ («{marker}»)")
            core_hit = True
            break  # Apply once

    # EOTC Identity/Titles/Patristics (+25 if canonical matched, else +35)
    identity_hit = False
    for marker in EOTC_IDENTITY_MARKERS:
        norm_marker = normalize_amharic(marker)
        if norm_marker and norm_marker in norm_text:
            pts = 25.0 if canonical_hit else 35.0
            score += pts
            matched_reasons.append(f"የኦርቶዶክስ ተዋሕዶ ማንነት/ደራሲ/ማዕረግ («{marker}»)")
            identity_hit = True
            break  # Apply once

    # Source channel verification (+25)
    channel_hit = False
    for marker in EOTC_CHANNEL_MARKERS:
        norm_marker = normalize_amharic(marker)
        if norm_marker and (norm_marker in norm_channel or norm_marker in source_channel_title.lower()):
            score += 25.0
            matched_reasons.append(f"የተረጋገጠ የኦርቶዶክስ ቻናል ምንጭ («{source_channel_title}»)")
            channel_hit = True
            break

    score = min(score, 100.0)

    if score >= LOCAL_APPROVAL_THRESHOLD and (canonical_hit or core_hit or identity_hit):
        return {
            "is_orthodox": True,
            "score": score,
            "category": "Orthodox",
            "reason": f"በአገር ውስጥ ማጣሪያ ጸድቋል: {', '.join(matched_reasons)}",
            "verified_by": "local_rules"
        }

    # If score is lower, it needs helper verification or safe fallback
    return {
        "is_orthodox": False,
        "score": score,
        "category": "Orthodox" if score >= 40 else "Unknown",
        "reason": f"ተጨማሪ ማጣራት ያስፈልገዋል (ነጥብ: {score:.1f}/100)",
        "verified_by": "pending_helper"
    }
