import asyncio
import re
from typing import Dict, Any, List, Optional
from telethon.tl.types import InputMessagesFilterDocument, DocumentAttributeFilename, Channel, Chat
from app.telegram.client import telegram_manager
from app.database import is_file_processed, record_processed_file, get_settings
from app.config import logger
from app.books.gemini_verifier import verify_book_with_gemini

TARGET_CHANNEL_LINK = "https://t.me/+2EsS9AQ1kt9mYmFk"
TARGET_BOOK_GOAL = 5000

# የታወቁ ዋና ዋና የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ ቴሌግራም ቻናሎች
KNOWN_ORTHODOX_CHANNELS = [
    "@EOTCBooks1",            # EOTC Books ⛪️
    "@menfesawimetshahft",     # መንፈሳዊ መጽሐፍ በpdf
    "@zikirekdusn",           # ዝክረ ቅዱሳን
    "@and_metshaf",           # ፩ መጽሐፍ
    "@OrthoT",                # የኦርቶዶክስ ተዋህዶ መጽሀፍት
    "@menfesawimethaf",       # መንፈሳዊ መጽሐፍ በpdf
    "@Orthodox_Books",        # ኦርቶዶክሳዊ ቅዱሳት መጻሕፍት & APPS
    "@ye_orthodox_tewahdo_mezmurat",
    "@orthodox_books_pdf",
    "@Tewahedo_Books",
    "@debretabor",
    "@mahiberekidusan",
    "@eotc_andimta",
    "@KidusatMetshaf",
    "@EOTC_Books_PDF",
    "@mahbere_kidusan",
    "@sinkisar_eotc",
    "@gedlat_we_dersanat",
    "@andimta_tergwame",
    "@ortodoxmezmur",
    "@eotcgssu21",
    "@fkteklehaymanot",
    "@orthodoxia_tewahido",
    "@kidusat_metsihaft",
    "@eotc_books",
    "@orthodoxtewahdo_books",
    "@ye_tewahedo_metsihaf",
    "@orthodox_mezmur_debter",
    "@tewahedomezmuroch",
    "@eotclibrary",
    "@kidusan_debter",
    "@tewahedo_haymanotie"
]

# ለግሎባል ፍለጋ (Global Document Search across all Telegram repositories)
GLOBAL_SEARCH_KEYWORDS = [
    # 1. ገድላት እና ቅዱሳን
    "ገድለ", "ገድሊ", "ተአምረ ማርያም", "ተአምረ ኢየሱስ", "ገድለ ተክለሃይማኖት",
    "ገድለ ጊዮርጊስ", "ገድለ ገብረመንፈስቅዱስ", "ገድለ አረጋዊ", "ገድለ አቡነ ሀብተማርያም",
    "ገድለ አርሴማ", "ገድለ ክርስቶስ ሠምራ", "ገድለ ወለተ ጴጥሮስ", "ገድለ እስጢፋኖስ",
    "ገድለ አባ ጊዮርጊስ ዘጋስጫ", "ገድለ ላሊበላ", "ዜና ቅዱሳን", "ገድለ ሐዋርያት",
    "ገድለ ቂርቆስ", "ገድለ መርቆሬዎስ", "ገድለ ፋሲለደስ", "ገድለ ዮሐንስ መጥምቅ",
    
    # 2. ድርሳናት እና መላእክት
    "ድርሳነ", "ድርሳን", "ድርሳነ ሚካኤል", "ድርሳነ ገብርኤል", "ድርሳነ ሩፋኤል",
    "ድርሳነ ዑራኤል", "ድርሳነ ራጉኤል", "ድርሳነ ፋኑኤል", "ድርሳነ ማኅየዊ", "ድርሳነ ሰንበት",
    "ድርሳነ ጎልጎታ", "ድርሳነ መስቀል", "ድርሳነ ኪዳነ ምሕረት",
    
    # 3. የጸሎት፣ የመልክዕ እና የምስጋና መጻሕፍት
    "መልክዐ", "መልክአ", "ውዳሴ ማርያም", "ሰይፈ ሥላሴ", "አርጋኖን", "ውዳሴ አምላክ",
    "መዝሙረ ዳዊት", "የዳዊት መዝሙር", "መልክአ ጊዮርጊስ", "መልክአ ሚካኤል", "መልክአ ገብርኤል",
    "መልክአ ኢየሱስ", "መልክአ ማርያም", "መልክአ ተክለሃይማኖት", "አንቀጸ ብርሃን", "ይዌድስዋ",
    "ሰይፈ መለኮት", "መዝሙረ ድንግል", "ውዳሴ ሰማዕታት", "ሰዓታት ዘሌሊት", "የዘወትር ጸሎት",
    
    # 4. አንድምታ እና የመጽሐፍ ቅዱስ ትርጓሜያት
    "አንድምታ", "ትርጓሜ", "ትርጓሜያት", "የወንጌል አንድምታ", "የጳውሎስ መልእክት አንድምታ",
    "የሐዋርያት ሥራ አንድምታ", "ራእየ ዮሐንስ አንድምታ", "ዘፍጥረት አንድምታ", "ዘጸአት አንድምታ",
    "ዘሌዋውያን አንድምታ", "ዘኁልቁ አንድምታ", "ዘዳግም አንድምታ", "ኢሳይያስ አንድምታ",
    "ትንቢተ ዳንኤል አንድምታ", "ሕዝቅኤል አንድምታ", "ምሳሌ አንድምታ", "መክብብ አንድምታ", "መኃልይ አንድምታ",
    "ሲራክ አንድምታ", "ሔኖክ አንድምታ", "ጦቢት አንድምታ", "ዮዲት አንድምታ", "መቃብያን አንድምታ",
    "ኩፋሌ", "ጥበበ ሰሎሞን", "ማቴዎስ ወንጌል አንድምታ", "ዮሐንስ ወንጌል አንድምታ",
    
    # 5. የዜማ፣ የቅዳሴ እና የማኅሌት መጻሕፍት
    "ሥርዓተ ቅዳሴ", "መጽሐፈ ቅዳሴ", "ቅዳሴ ንባቡና ትርጓሜው", "ሰዓታት", "ጾመ ድጓ", "ድጓ",
    "መጽሐፈ ዝማሬ", "መዋሥዕት", "መጽሐፈ ምዕራፍ", "ሥርዓተ አቋቋም", "ቅዱስ ያሬድ", "ማኅሌተ ጽጌ", "ማኅሌት", "ዝማሬ መላእክት",
    "ዚቅ", "መዝሙረ ቅዱሳን", "የቅዳሴ ትርጓሜ",
    
    # 6. ትምህርተ ሃይማኖት፣ ነገረ መለኮት እና ፍትሐ ነገሥት
    "ሃይማኖተ አበው", "ፍትሐ ነገሥት", "መጽሐፈ ምስጢር", "ባሕረ ሐሳብ", "ስንክሳር",
    "መጽሐፈ ኪዳን", "ትምህርተ ኅቡዓት", "ነገረ ማርያም", "ነገረ ክርስቶስ", "ነገረ ድኅነት",
    "አምደ ሃይማኖት", "ኮኩሐ ሃይማኖት", "ምስጢረ ሥላሴ", "ምስጢረ ሥጋዌ", "ምስጢረ ጥምቀት",
    
    # 7. የአበው እና የመነኮሳት ትምህርት
    "አረጋዊ መንፈሳዊ", "ማር ይስሐቅ", "ፊልክስዩስ", "ዜና አበው", "መጽሐፈ ገነት",
    "መጽሐፈ ሐዊ", "ዜና አይሁድ", "መጽሐፈ ፈውስ", "ተግሣጸ አበው", "ዮሐንስ አፈወርቅ",
    
    # 8. የቀኖና፣ የዲድስቅልያ፣ የገዳማት እና የጥንታዊ ብራና መጻሕፍት
    "ዲድስቅልያ", "ፍትሐ ነገሥት ንባቡና ትርጓሜው", "የሐዋርያት ቀኖና", "መርሐ ጽድቅ",
    "ተግሣጽ ወመክሥት", "አቡሻክር", "መጽሐፈ ብርሃን", "ቀኖና ቤተክርስቲያን", "መጽሐፈ ግንዘት",
    "ሥርዓተ ተክሊል", "መጽሐፈ ቄደር", "የግእዝ ሰዋስው", "ልሳነ ግእዝ", "ምክረ አበው", "የገዳማት ታሪክ"
]

# የኦርቶዶክስ ተዋሕዶ ቁልፍ ቃላት (Orthodox Keywords for Validation)
ORTHODOX_KEYWORDS = [
    "ገድል", "ድርሳን", "አንድምታ", "ትርጓሜ", "ትርጓሜያት", "ቅዳሴ", "ውዳሴ", "ሰዓታት", 
    "ድጓ", "ጾመ ድጓ", "ፆመ ድጓ", "መጽሐፈ ምዕራፍ", "ዝማሬ", "መዋሥዕት", "ነገረ", "ሃይማኖተ", "ክብረ ነገሥት", "ተአምረ", "ተአምር",
    "ብሉያት", "ሐዲሳት", "ወንጌል", "ጳውሎስ", "መዝሙረ ዳዊት", "የዳዊት መዝሙር", "ሲራክ", "ሔኖክ", "ሄኖክ", "ጦቢት", "ዮዲት",
    "ኢሳይያስ", "ኤርሚያስ", "ሕዝቅኤል", "ህዝቅኤል", "መቃብያን", "መጽሐፈ", "ፍትሐ ነገሥት", "ስንክሳር", "ሥንክሳር",
    "ሃይማኖት", "ተዋሕዶ", "ኦርቶዶክስ", "ቤተክርስቲያን", "ማኅበረ ቅዱሳን", "ማህበረ ቅዱሳን",
    "ዝክረ ቅዱሳን", "ምስጢረ", "ዜና ቅዱሳን", "ቅዱስ", "ቅድስት", "አቡነ", "ማርያም", "ማሪያም",
    "መነኮሳት", "አረጋዊ መንፈሳዊ", "ማር ይስሐቅ", "ፊልክስዩስ", "ባሕረ ሐሳብ", "ሥርዓተ ቤተክርስቲያን", 
    "ፍትሐት", "መጠምቂያ", "ተክሊል", "ቀኖና", "ዶግማ", "ቃለ እግዚአብሔር",
    "ተዋህዶ", "ክርስቲያን", "ክርስቶስ", "እግዚአብሔር", "መልአክ", "መላእክት", "ጻድቅ", "ሰማዕት",
    "ዮሐንስ", "ዮሀንስ", "ጴጥሮስ", "ጊዮርጊስ", "ተክለ ሃይማኖት", "ገብረ መንፈስ", "ሚካኤል", "ገብርኤል",
    "ሩፋኤል", "ኡራኤል", "ፋኑኤል", "አስቴር", "ትንቢተ", "ትንቢት", "ዳንኤል", "ዳንዔል", "ሆሴዕ", "ሆሴእ", "አሞጽ", "አሞፅ",
    "ሚክያስ", "ኢዩኤል", "አብድዩ", "ዮናስ", "ናሆም", "ዕንባቆም", "እንባቆም", "ሶፎንያስ", "ሐጌ", "ሀጌ", "ዘካርያስ", "ሚልክያስ",
    "ኦሪት", "ዘፍጥረት", "ዘጸአት", "ዘፀአት", "ዘሌዋውያን", "ዘኁልቁ", "ዘሁልቁ", "ዘዳግም", "ኢያሱ", "መሳፍንት", "ሩት", "ሳሙኤል",
    "ነገሥት", "ዜና መዋዕል", "ዕዝራ", "እዝራ", "ነህምያ", "ኢዮብ", "ምሳሌ", "መክብብ", "መኃልይ", "መሀልይ", "ጥበብ",
    "ማቴዎስ", "ማርቆስ", "ሉቃስ", "ሐዋርያት", "ሮሜ", "ቆሮንቶስ", "ገላትያ", "ኤፌሶን", "ፊልጵስዩስ", "ቆላስይስ", "ተሰሎንቄ",
    "ጢሞቴዎስ", "ቲቶ", "ፊልሞና", "ዕብራውያን", "እብራውያን", "ያዕቆብ", "ይሁዳ", "ራእይ", "ራእየ", "ራዕይ",
    "መጽሐፈ ምስጢር", "ሃይማኖተ አበው", "ውዳሴ ማርያም", "አርጋኖን", "ሰይፈ ሥላሴ",
    "ሥላሴ", "መልክአ", "መልከአ", "ዜና አይሁድ", "መጽሐፈ ፈውስ", "መጽሐፈ ተግሣጽ", "መጽሐፈ ምሳሌ",
    "አቡሻክር", "መጽሐፈ ብርሃን", "መጽሐፈ ባሕርይ", "ዲድስቅልያ", "ኩፋሌ", "ሰዋስው", "ግእዝ", "ግዕዝ",
    "ያሬድ", "አቋቋም", "ዚቅ", "ማኅሌት", "ማኅሌተ ጽጌ", "መዝሙር", "ቅኔ", "መጽሐፈ ግንዘት", "መጽሐፈ ቄደር",
    "homilies", "theology", "patrology", "eotc", "tewahedo", "orthodox", "tsome degua", "degua", "yared"
]

DISALLOWED_SOURCES = [
    "education", "bureau", "ትምህርት", "ቢሮ", "school", "academy", 
    "university", "college", "fetena", "matric", "ministry", "minister",
    "tikusat", "home of book", "amharicbook", "amharic book", "movies", 
    "tech", "pdf store", "book store", "novels", "fiction", 
    "news", "media", "press", "politics", "zone", "digital library",
    "ethiopian digital library", "addis ababa education bureau", "ministry of education"
]

def is_definitely_fiction_or_secular(filename: str, caption: str) -> bool:
    """በቻናሉ ውስጥ የተላኩ ልብወለዶች፣ የትምህርት ቤት ሰነዶች እና ዓለማዊ ፋይሎችን ለይቶ ለማጥፋት ያገለግላል"""
    fn = filename.lower()
    cap = caption.lower()
    full_text = f"{fn} {cap}"

    # 1. የትምህርት ቤት መጻሕፍት (ሒሳብ፣ ሳይንስ፣ ክፍል፣ Grade፣ ፈተና ወዘተ)
    school_terms = [
        "ሒሳብ", "math", "mathematics", "ማትስ", "ፊዚክስ", "physics", 
        "ኬሚስትሪ", "chemistry", "ባዮሎጂ", "biology", "አጠቃላይ ሳይንስ", "general science", 
        "social studies", "textbook", "curriculum", "fetena", "matric", 
        "exam", "worksheet", "work sheet", "የተማሪ መጽሐፍ", "መምህር መምሪያ"
    ]
    if any(k in full_text for k in school_terms):
        return True

    if "ሳይንስ" in full_text and not any(ok in full_text for ok in ["መጽሐፍ ቅዱስ", "ቅዱሳን", "ሃይማኖት", "ስምምነት", "ተዋሕዶ", "ኦርቶዶክስ"]):
        return True

    if any(s in full_text for s in ["addis ababa education bureau", "ministry of education", "ትምህርት ቢሮ", "ethiopian digital library"]):
        return True

    if re.search(r"\b([1-9]|1[0-2])ኛ\s*ክፍል", fn) or re.search(r"grade\s*([1-9]|1[0-2])", fn):
        return True

    if "part " in fn and any(k in fn for k in ["ሒሳብ", "ምዕራፍ 5", "ምዕራፍ 6", "ምዕራፍ 1", "ምዕራፍ 2", "ምዕራፍ 3", "ምዕራፍ 4"]):
        return True

    # 2. የተረጋገጡ ልብወለዶች እና ዓለማዊ መጻሕፍት
    known_fictions = [
        "ፍቅር እስከ መቃብር", "ፍቅር እስከ", "ኦሮማይ", "በዓሉ ግርማ", "ሐዲስ አለማየሁ",
        "ትኩሳት", "ሌቱም_አይነጋልኝ", "ሌቱም አይነጋልኝ", "አለመኖር", "ወንጀል እና ቅጣት", 
        "ዶስቶየቭስኪ", "ስብሐት ገብረእግዚአብሔር", "ስብሀት", "ጳውሎስ ኞኞ", "ጸጋዬ ገብረ", 
        "ዳንኤል ክብረት", "ተስፋዬ ገብረአብ", "የቡርቃ_ዝምታ", "የቡርቃ ዝምታ", "ዳንኤል ተረፈ", 
        "ዳንኤል ሲልቫ", "ሞሳድ", "በርታ ክሌይ", "የውበት ወጥመድ", "ሳይኮሎጂ", 
        "በራስ መተማመን", "የፍቅር ታሪክ", "ሮማንስ", "fiction", "novel", "ልብወለድ", "ልቦለድ",
        "goodamharicbooks", "kooblife", "ደስፔንዛ", "አእምሮህ", "ገብረ-ክርስቶሰ ደስታ",
        "የሰርቆ_አደሮች", "ፍቅርና ሀገር", "አርዐያ", "ከበደ ሚካኤል", "ያዕቆብ_ኃይለማርያም", "አሰብ",
        "ኅሩይ ወልደ", "የደም ዕንባ", "ዳዊት ወልደጊዮርጊስ", "ኤርሚያስ አመልጋ", "ስሞተኛው", "ይኩኖ",
        "ቴዎድሮስ እስከ ቀዳማዊ", "ተክለጻድቅ መኩርያ", "መንግስቱ ኃይለ", "ትግላችን", "ማፊያ", "ወዳጄነህ"
    ]
    for kf in known_fictions:
        if kf in full_text or kf in fn:
            return True

    # 3. የፖለቲካ እና የሰልፍ መግለጫዎች
    if any(m in fn for m in ["መግለጫ", "የሰልፍ ጥሪ", "ኮሚቴ መግለጫ", "ኢህአፓ", "ህልፈተ አንጃ"]):
        return True

    return False

# የማይገቡ (ልብወለድ፣ ፖለቲካ፣ ዓለማዊ ወይም የሌላ እምነት መጻሕፍት)
REJECT_KEYWORDS = [
    "ልብወለድ", "ልቦለድ", "fiction", "novel", "ታሪካዊ ልብወለድ", "ዘፈን", "ሙዚቃ", 
    "ፖለቲካ", "መጽሔት", "ጋዜጣ", "ወሬ", "ስፖርት", "እግር ኳስ", "ፍልስፍና", 
    "ፍቅር እና", "የፍቅር ታሪክ", "የፍቅር ግጥም", "አፍቃሪ", "romance", "poetry",
    "ፕሮቴስታንት", "ፔንቴ", "ጴንጤ", "እስልምና", "ቁርአን", "ቁርዓን", "ሙስሊም", "ሐዲስ",
    "ፓስተር", "ነቢይ ሱራፌል", "ነብይ", "ዮናታን", "እዩ ጩፋ", "ነፃ አውጪ", "ትግል",
    "ትኩሳት", "ቆርጠሀት", "ያገር ልጅ", "በራስ መተማመን", "የተናቁ ዕንቁዎች", "ጠያይም መላእክት",
    "እኮ እንዴት", "የነጋሶ መንገድ", "ዳንኤል ተረፈ", "ሳይላክ የቀረ", "ህልፈተ አንጃ", "ኢህአፓ",
    "መንገድ ስጡኝ", "የከፍተኛ ትምህርት", "ጳውሎስ ኞኞ", "ሀሁ በስድስት ወር", "ጸጋዬ ገብረ",
    "የጉድጓዱ ምስጢር", "ገዳሙ ገዛኸኝ", "ደገልሃን", "ጌታቸው ጳውሎስ", "አዜብ", "መስፍን ሀብተማርያም",
    "የደም ዕንባ", "ዳዊት ወልደጊዮርጊስ", "ኤርሚያስ አመልጋ", "ስሞተኛው", "ይኩኖ", "ቴዎድሮስ እስከ ቀዳማዊ",
    "ተክለጻድቅ መኩርያ", "መንግስቱ ኃይለ", "ትግላችን", "የቡርቃ_ዝምታ", "ተስፋዬ ገብረአብ", "ማፊያ",
    "ወዳጄነህ", "ምኒልክ", "ዳንኤል ክብረት", "goodamharicbooks", "kooblife", "እፍታ", "ደስፔንዛ",
    "አእምሮህ", "ገብረ-ክርስቶሰ ደስታ", "የሰርቆ_አደሮች", "ፍቅርና ሀገር", "አርዐያ", "ከበደ ሚካኤል",
    "አለመኖር", "ሌቱም_አይነጋልኝ", "ስብሀት", "ስብሐት", "ያዕቆብ_ኃይለማርያም", "አሰብ", "ኅሩይ ወልደ",
    "ወንጀል እና ቅጣት", "ዶስቶየቭስኪ", "በርታ ክሌይ", "የውበት ወጥመድ", "ሳይኮሎጂ", "ሳይኮሎጂካል",
    "ሞሳድ", "ሲልቫ", "ስለላ", "መርማሪ", "ክፍለ ጦር", "ወታደራዊ", "ተልዕኮ", "ዳንኤል ሲልቫ",
    "መግለጫ", "ሰልፍ", "ኮሚቴ", "ኮሜቴ", "ደንብ", "መተዳደሪያ", "ሪፖርት", "አጀንዳ", "ደቂቃ", "ስብሰባ",
    "ሒሳብ", "math", "mathematics", "ፊዚክስ", "physics", "ኬሚስትሪ", "chemistry", "ባዮሎጂ", "biology",
    "ጂኦግራፊ", "geography", "ሳይንስ", "science", "አጠቃላይ ሳይንስ", "social studies", "ህብረተሰብ ጥናት",
    "ዜግነት", "citizenship", "ስነ ዜጋ", "ict", "ኢኮኖሚክስ", "economics", "አካውንቲንግ", "accounting",
    "textbook", "bureau", "education", "ትምህርት ቢሮ", "curriculum", "ሥርዓተ ትምህርት", "matric", "fetena", "ፈተና", "ሞዴል ፈተና",
    "1ኛ ክፍል", "2ኛ ክፍል", "3ኛ ክፍል", "4ኛ ክፍል", "5ኛ ክፍል", "6ኛ ክፍል", "7ኛ ክፍል", "8ኛ ክፍል", "9ኛ ክፍል", "10ኛ ክፍል", "11ኛ ክፍል", "12ኛ ክፍል",
    "grade 1", "grade 2", "grade 3", "grade 4", "grade 5", "grade 6", "grade 7", "grade 8", "grade 9", "grade 10", "grade 11", "grade 12"
]

def is_orthodox_book(filename: str, caption: str) -> bool:
    """Strictly filter for legitimate Orthodox spiritual books."""
    text = (filename + " " + caption).lower()

    # በመጀመሪያ የማይገቡትን እንፈትሽ
    for r in REJECT_KEYWORDS:
        if r in text:
            if r in ("ፍቅር", "የፍቅር"):
                spiritual_love = ["ፍቅረ እግዚአብሔር", "ፍቅረ መስቀል", "ፍቅረ ቅዱሳን"]
                if any(h in text for h in spiritual_love):
                    continue
            return False

    # የኦርቶዶክስ ቁልፍ ቃላትን እንፈትሽ
    for k in ORTHODOX_KEYWORDS:
        if k in text:
            return True

    return False

def classify_orthodox_book(filename: str, caption: str) -> Dict[str, str]:
    """መጽሐፉን በይዘቱ መርምሮ ትክክለኛውን ምድብ፣ ተዛማጅ ኢሞጂ እና ሃሽታግ ይሰጣል።"""
    text = (filename + " " + caption).lower()

    # 1. ገድላት እና ድርሳናት
    if any(k in text for k in ["ገድለ", "ገድሊ", "ድርሳነ", "ድርሳን", "ተአምረ", "ተአምር", "ዜና ቅዱሳን", "ሰማዕት", "ጻድቅ", "አቡነ"]):
        return {
            "name": "ገድላት እና ድርሳናት (Hagiography)",
            "emoji": "⚔️",
            "hashtag": "#ገድላት_እና_ድርሳናት #ቅዱሳን #ተአምራት"
        }

    # 2. አንድምታ እና የመጽሐፍ ቅዱስ ትርጓሜ
    if any(k in text for k in ["አንድምታ", "ትርጓሜ", "ትርጓሜያት", "ብሉያት", "ሐዲሳት", "ወንጌል", "ጳውሎስ", "ኦሪት", "ኢሳይያስ", "ዳንኤል", "ኤርሚያስ", "ሲራክ", "ሔኖክ", "መጽሐፈ ኪዳን"]):
        return {
            "name": "አንድምታ እና የመጽሐፍ ቅዱስ ትርጓሜ (Biblical Commentaries)",
            "emoji": "📖",
            "hashtag": "#አንድምታ_ትርጓሜ #የመጽሐፍ_ቅዱስ_ጥናት #ብሉይ_እና_ሐዲስ"
        }

    # 3. የጸሎት፣ የመልክዕ እና የውዳሴ መጻሕፍት
    if any(k in text for k in ["መልክአ", "መልክዐ", "ውዳሴ", "ሰይፈ", "ጸሎት", "ምስጋና", "አርጋኖን", "መዝሙረ ዳዊት", "ዳዊት"]):
        return {
            "name": "የጸሎት እና የመልክዕ መጻሕፍት (Liturgical Prayers & Praises)",
            "emoji": "🕯",
            "hashtag": "#የጸሎት_መጻሕፍት #መልክአ_ቅዱሳን #ውዳሴ_ማርያም"
        }

    # 4. የዜማ፣ የቅዳሴ እና የማኅሌት መጻሕፍት
    if any(k in text for k in ["ቅዳሴ", "ሰዓታት", "ድጓ", "ጾመ ድጓ", "ዝማሬ", "መዋሥዕት", "ምዕራፍ", "ማኅሌት", "አቋቋም", "ያሬድ", "ዚቅ"]):
        return {
            "name": "የዜማ እና የሥርዓተ ቅዳሴ መጻሕፍት (Chant & Liturgy)",
            "emoji": "🎼",
            "hashtag": "#የዜማ_መጻሕፍት #ሥርዓተ_ቅዳሴ #ቅዱስ_ያሬድ"
        }

    # 5. ትምህርተ ሃይማኖት፣ ነገረ መለኮት እና ፍትሐ ነገሥት
    if any(k in text for k in ["ሃይማኖተ አበው", "ፍትሐ ነገሥት", "መጽሐፈ ምስጢር", "ነገረ ማርያም", "ነገረ ድኅነት", "ነገረ ክርስቶስ", "ቀኖና", "ዶግማ", "ትምህርተ", "ሃይማኖት"]):
        return {
            "name": "ትምህርተ ሃይማኖት እና ነገረ መለኮት (Theology & Dogma)",
            "emoji": "⛪️",
            "hashtag": "#ትምህርተ_ሃይማኖት #ነገረ_መለኮት #ኦርቶዶክስ_ተዋሕዶ"
        }

    # 6. የቤተክርስቲያን ታሪክ፣ ስንክሳር እና ባሕረ ሐሳብ
    if any(k in text for k in ["ስንክሳር", "ባሕረ ሐሳብ", "ክብረ ነገሥት", "ታሪክ", "ዜና አይሁድ", "ዜና አበው", "መጽሐፈ ገነት"]):
        return {
            "name": "የቤተክርስቲያን ታሪክ እና ባሕረ ሐሳብ (Church History & Computus)",
            "emoji": "📜",
            "hashtag": "#የቤተክርስቲያን_ታሪክ #ስንክሳር #ባሕረ_ሐሳብ"
        }

    # 7. የመነኮሳት እና የመንፈሳዊ ሕይወት መጻሕፍት
    if any(k in text for k in ["ማር ይስሐቅ", "ፊልክስዩስ", "አረጋዊ መንፈሳዊ", "መነኮሳት", "ተግሣጽ", "ምክር"]):
        return {
            "name": "የመነኮሳት ትምህርት እና መንፈሳዊ ሕይወት (Monastic & Spiritual Life)",
            "emoji": "🕊",
            "hashtag": "#መንፈሳዊ_ሕይወት #መነኮሳት #ተግሣጽ"
        }

    return {
        "name": "የኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጽሐፍ",
        "emoji": "📚",
        "hashtag": "#ኦርቶዶክሳዊ_መጽሐፍ #ኦርቶዶክስ_ተዋሕዶ"
    }

class OrthodoxHarvester:
    _instance: Optional["OrthodoxHarvester"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OrthodoxHarvester, cls).__new__(cls)
            cls._instance.is_running = False
            cls._instance._stop_requested = False
            cls._instance.current_task: Optional[asyncio.Task] = None
            cls._instance.stats = {
                "analyzed": 0,
                "forwarded": 0,
                "duplicates": 0,
                "rejected": 0,
                "current_channel": "",
                "last_forwarded": ""
            }
        return cls._instance

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "target_channel": TARGET_CHANNEL_LINK,
            "target_goal": TARGET_BOOK_GOAL,
            "stats": self.stats
        }

    async def start(self):
        if self.is_running:
            return {"success": False, "message": "የመጽሐፍት ማሰባሰቢያው አስቀድሞ እየሰራ ነው"}
        
        # ቀደም ሲል የተላኩትን ከዳታቤዝ እናስብብ
        try:
            from app.database import get_db_connection
            async with get_db_connection() as db:
                async with db.execute("SELECT COUNT(*) FROM processed_files WHERE status = 'sent'") as cur:
                    row = await cur.fetchone()
                    if row:
                        self.stats["forwarded"] = row[0]
        except Exception as dbe:
            logger.warning("Could not sync forwarded count from DB: %s", dbe)

        self.is_running = True
        self._stop_requested = False
        self.current_task = asyncio.create_task(self._harvest_loop())
        logger.info("Orthodox Harvester task spawned successfully (Current sent: %d / Goal: %d).", self.stats["forwarded"], TARGET_BOOK_GOAL)
        return {"success": True, "message": "የኦርቶዶክስ መጽሐፍት ማሰባሰቢያ በተሳካ ሁኔታ ተጀምሯል"}

    def stop(self):
        if not self.is_running:
            return {"success": False, "message": "የመጽሐፍት ማሰባሰቢያው አልጀመረም"}
        self._stop_requested = True
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        self.is_running = False
        logger.info("Orthodox Harvester stopped by user.")
        return {"success": True, "message": "የኦርቶዶክስ መጽሐፍት ማሰባሰቢያ ቆሟል"}

    async def delete_fictions_from_channel(self) -> Dict[str, Any]:
        """በዒላማው ቻናል ውስጥ የተላኩ ልብወለድና ዓለማዊ መልእክቶችን መርምሮ በቅጽበት ያጠፋል"""
        client = telegram_manager.client
        if not client or not client.is_connected() or not await client.is_user_authorized():
            return {"success": False, "message": "Telegram not connected"}

        settings = await get_settings()
        dest_target = settings.get("target_channel") or TARGET_CHANNEL_LINK

        try:
            dest_entity = await client.get_entity(dest_target)
        except Exception as e:
            return {"success": False, "message": f"Could not access channel: {e}"}

        to_delete_ids = set()
        deleted_names = []

        logger.info("Deep scanning target channel for fiction/secular messages to delete...")

        # 1. በቁልፍ ቃላት በሰርቨር ደረጃ መፈለግ (ሒሳብ፣ Education፣ Grade ወዘተ በሙሉ ቻናሉ ውስጥ መፈለግ)
        targeted_searches = [
            "ሒሳብ", "Addis Ababa", "Education Bureau", "Ethiopian Digital Library", 
            "Biology", "Physics", "Chemistry", "Grade", "ምዕራፍ 6", "ምዕራፍ 5", "ትኩሳት", 
            "አለመኖር", "ሌቱም አይነጋልኝ", "ወንጀል እና ቅጣት", "ዶስቶየቭስኪ"
        ]
        for term in targeted_searches:
            try:
                async for msg in client.iter_messages(dest_entity, search=term, limit=300):
                    fn = ""
                    if msg.document:
                        for attr in msg.document.attributes:
                            if isinstance(attr, DocumentAttributeFilename):
                                fn = attr.file_name
                                break
                    text = f"{fn} {msg.text or ''}".lower()
                    if is_definitely_fiction_or_secular(fn, text):
                        if msg.id not in to_delete_ids:
                            to_delete_ids.add(msg.id)
                            deleted_names.append(fn or f"Msg ID {msg.id}")
            except Exception as se:
                logger.warning("Error searching channel for term '%s': %s", term, se)

        # 2. የቅርብ 500 መልእክቶችን አጠቃላይ መቃኘት
        async for msg in client.iter_messages(dest_entity, limit=500):
            if msg.id in to_delete_ids:
                continue
            fn = ""
            if msg.document:
                for attr in msg.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        fn = attr.file_name
                        break
            text = f"{fn} {msg.text or ''}".lower()

            if is_definitely_fiction_or_secular(fn, text):
                to_delete_ids.add(msg.id)
                deleted_names.append(fn or f"Msg ID {msg.id}")

        del_list = list(to_delete_ids)
        if del_list:
            batch_size = 50
            for i in range(0, len(del_list), batch_size):
                chunk = del_list[i:i + batch_size]
                await client.delete_messages(dest_entity, chunk)
                await asyncio.sleep(0.5)
            logger.info("Successfully deleted %d secular/school/fiction messages from target channel: %s", len(del_list), deleted_names)

        return {
            "success": True,
            "deleted_count": len(del_list),
            "deleted_books": deleted_names
        }

    async def _discover_user_orthodox_sources(self, client) -> List[Any]:
        user_sources = []
        try:
            logger.info("Discovering user's joined Orthodox channels and groups...")
            async for dialog in client.iter_dialogs(limit=300):
                entity = dialog.entity
                if isinstance(entity, (Channel, Chat)):
                    title = getattr(entity, "title", "") or ""
                    un = getattr(entity, "username", "") or ""
                    t = (title + " " + un).lower()
                    
                    if "atsedeteguhan" in t or "2ess9aq1kt9mymfk" in t:
                        continue

                    # አጠቃላይ የመጻሕፍት ግሩፖችን እና ሌሎች ልብወለድ፣ ዜና፣ ሚዲያና ትምህርት ቢሮ ያለባቸውን እናስወግዳለን
                    if any(b in t for b in DISALLOWED_SOURCES):
                        continue

                    is_orthodox = any(
                        term in t 
                        for term in ["ኦርቶዶክስ", "ተዋሕዶ", "ተዋህዶ", "eotc", "orthodox", "ቤተክርስቲያን", "መንፈሳዊ", "ቅዱሳን", "ዝክረ", "ማኅበረ"]
                    )
                    if is_orthodox:
                        user_sources.append(entity)
                        logger.info("Found user Orthodox source: '%s' (ID: %s)", title, entity.id)
        except Exception as e:
            logger.error("Error discovering user dialogs: %s", e)
        return user_sources

    async def _process_and_forward_message(self, client, dest_entity, msg, source_title: str):
        """እያንዳንዱን መልዕክት መርምሮ ወደ ዒላማ ቻናል ያስተላልፋል"""
        if not msg.document:
            return False

        self.stats["analyzed"] += 1

        filename = ""
        for attr in msg.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                filename = attr.file_name
                break

        if not filename:
            ext = msg.file.ext or ".pdf"
            filename = f"orthodox_book_{msg.id}{ext}"

        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext not in ("pdf", "epub", "djvu"):
            return False

        caption = msg.text or ""

        # 0. የመጀመሪያ ደረጃ ፍተሻ፡ የምንጭ ስም ጥብቅ ፍተሻ (ትምህርት ቢሮ፣ ዜና እና ዓለማዊ ምንጮችን መከልከል)
        s_title = source_title.lower()
        if any(b in s_title for b in DISALLOWED_SOURCES):
            self.stats["rejected"] += 1
            logger.info("🛑 [VERIFY REJECTED] Disallowed source '%s' for file '%s'", source_title, filename)
            return False

        # 1. ሁለተኛ ደረጃ ፍተሻ፡ ልብወለድ እና የትምህርት ቤት መጻሕፍትን በጥብቅ ማገድ
        if is_definitely_fiction_or_secular(filename, caption):
            self.stats["rejected"] += 1
            logger.info("🛑 [VERIFY REJECTED] Secular/School/Fiction detected: '%s' (Source: %s)", filename, source_title)
            return False

        # 2. ሦስተኛ ደረጃ ፍተሻ፡ ኦርቶዶክሳዊ መንፈሳዊ መጽሐፍ መሆኑን በጥብቅ ማረጋገጥ
        if not is_orthodox_book(filename, caption):
            self.stats["rejected"] += 1
            logger.info("🛑 [VERIFY REJECTED] Not verified as Orthodox spiritual book: '%s'", filename)
            return False

        # 3. አራተኛ ደረጃ ፍተሻ፡ ቀደም ሲል የተላከ መሆኑን መፈተሽ (Duplicates check)
        already_done = await is_file_processed(msg.chat_id, msg.id, filename)
        if already_done:
            self.stats["duplicates"] += 1
            return False

        # 4. አምስተኛ ደረጃ ፍተሻ፡ በ Gemini AI ጥብቅ ማረጋገጫ (Always Gemini Verify)
        gemini_check = await verify_book_with_gemini(filename, caption)
        if not gemini_check.get("is_orthodox", False):
            self.stats["rejected"] += 1
            logger.info("🛑 [GEMINI REJECTED] Secular/Unverified: '%s' (Reason: %s)", filename, gemini_check.get("reason"))
            return False

        logger.info("✅ [GEMINI & CODE PASSED] 100%% Authentic Orthodox Book: '%s' (Source: %s) -> Sending...", filename, source_title)

        clean_title = re.sub(r"\.(pdf|epub|djvu)$", "", filename, flags=re.IGNORECASE).replace("_", " ").strip()

        caption_text = (
            f"<i>ርዕስ:</i> <b>{clean_title}</b>\n"
            f"<i>ፋይል:</i> {filename}\n\n"
            f'<a href="https://t.me/atsedeteguhan">our telegram channel</a>\n\n'
            f"<b>አጸደ ትጉሃን ሰንበት ትምህርት ቤት</b>\n"
            f"<b>Atsede tguhan sunday school</b>"
        )

        try:
            # በ1 ሰከንድ ውስጥ በቀጥታ በቴሌግራም ክላውድ ማስተላለፍ
            await client.send_file(
                dest_entity,
                file=msg.media,
                caption=caption_text,
                parse_mode="html",
                force_document=True
            )
            self.stats["forwarded"] += 1
            self.stats["last_forwarded"] = filename

            await record_processed_file(
                requested_title=clean_title,
                author="Orthodox Church",
                source=source_title,
                telegram_chat_id=msg.chat_id,
                telegram_message_id=msg.id,
                filename=filename,
                file_size=msg.document.size or 0,
                confidence=100.0,
                status="sent"
            )

            logger.info("✅ [%d/%d] Forwarded: %s (Source: %s)", self.stats["forwarded"], TARGET_BOOK_GOAL, filename, source_title)
            await asyncio.sleep(1.8)
            return True

        except Exception as fe:
            logger.error("Error forwarding '%s': %s", filename, fe)
            err_str = str(fe).lower()
            if "flood" in err_str:
                wait_seconds = 30
                match = re.search(r"wait of (\d+) seconds", err_str)
                if match:
                    wait_seconds = int(match.group(1)) + 2
                logger.warning("Flood wait detected! Sleeping for %d seconds...", wait_seconds)
                await asyncio.sleep(wait_seconds)
            elif "connection" in err_str or "winerror" in err_str or "timeout" in err_str:
                logger.warning("Network glitch during forward. Retrying reconnection in 8s...")
                await asyncio.sleep(8)
                try:
                    await telegram_manager.init_client()
                except Exception:
                    pass
            return False

    async def _harvest_loop(self):
        client = telegram_manager.client
        if not client or not client.is_connected() or not await client.is_user_authorized():
            logger.error("Telegram client not connected/authorized.")
            self.is_running = False
            return

        settings = await get_settings()
        dest_target = settings.get("target_channel") or TARGET_CHANNEL_LINK

        try:
            dest_entity = await client.get_entity(dest_target)
            dest_title = getattr(dest_entity, "title", "Custom Channel")
            logger.info("Target destination verified: %s", dest_title)
        except Exception as e:
            logger.error("Failed to access target destination channel '%s': %s", dest_target, e)
            self.is_running = False
            return

        logger.info("=== Massive Orthodox Harvester Started (Goal: %d books) ===", TARGET_BOOK_GOAL)

        cycle = 1
        while not self._stop_requested and self.stats["forwarded"] < TARGET_BOOK_GOAL:
            logger.info("=== Orthodox Harvester Cycle %d (Current: %d / Goal: %d) ===", cycle, self.stats["forwarded"], TARGET_BOOK_GOAL)

            try:
                # --- ደረጃ 1፡ የታወቁ እና የተጠቃሚው ቻናሎችን መቃኘት ---
                user_sources = await self._discover_user_orthodox_sources(client)
                all_sources = []
                all_sources.extend(user_sources)
                for ch in KNOWN_ORTHODOX_CHANNELS:
                    all_sources.append(ch)

                for source in all_sources:
                    if self._stop_requested or self.stats["forwarded"] >= TARGET_BOOK_GOAL:
                        break

                    try:
                        if isinstance(source, str):
                            chat_entity = await client.get_entity(source)
                            chat_title = getattr(chat_entity, "title", source)
                        else:
                            chat_entity = source
                            chat_title = getattr(chat_entity, "title", str(source.id))

                        if getattr(chat_entity, "id", None) == getattr(dest_entity, "id", None):
                            continue

                        self.stats["current_channel"] = chat_title
                        logger.info("Scanning source: %s", chat_title)

                        async for msg in client.iter_messages(chat_entity, filter=InputMessagesFilterDocument, limit=800):
                            if self._stop_requested or self.stats["forwarded"] >= TARGET_BOOK_GOAL:
                                break
                            await self._process_and_forward_message(client, dest_entity, msg, chat_title)

                    except Exception as ce:
                        logger.warning("Could not access or iterate source '%s': %s", source, ce)
                        continue

                # --- ደረጃ 2፡ ግሎባል ፍለጋ (Global Search across all Public Repositories) ---
                if not self._stop_requested and self.stats["forwarded"] < TARGET_BOOK_GOAL:
                    logger.info("Starting Global Document Search across Telegram Public Repositories (Cycle %d)...", cycle)
                    for kw in GLOBAL_SEARCH_KEYWORDS:
                        if self._stop_requested or self.stats["forwarded"] >= TARGET_BOOK_GOAL:
                            break

                        self.stats["current_channel"] = f"Global Search: '{kw}'"
                        logger.info("Running Global Search for keyword: '%s'...", kw)

                        try:
                            async for msg in client.iter_messages(None, search=kw, filter=InputMessagesFilterDocument, limit=300):
                                if self._stop_requested or self.stats["forwarded"] >= TARGET_BOOK_GOAL:
                                    break

                                chat_name = "Global Library"
                                try:
                                    chat = await msg.get_chat()
                                    chat_name = getattr(chat, "title", "Global Library")
                                    if getattr(chat, "id", None) == getattr(dest_entity, "id", None):
                                        continue
                                except Exception:
                                    pass

                                await self._process_and_forward_message(client, dest_entity, msg, chat_name)

                        except Exception as ge:
                            logger.warning("Global search error for keyword '%s': %s", kw, ge)
                            if "flood" in str(ge).lower():
                                await asyncio.sleep(20)
                            continue

                cycle += 1
                if self.stats["forwarded"] < TARGET_BOOK_GOAL and not self._stop_requested:
                    logger.info("Cycle complete (Sent: %d / %d). Sleeping 10s before next pass...", self.stats["forwarded"], TARGET_BOOK_GOAL)
                    await asyncio.sleep(10)

            except asyncio.CancelledError:
                logger.info("Orthodox Harvester task cancelled.")
                break
            except Exception as e:
                logger.error("Unexpected error in Orthodox Harvester loop: %s", e)
                await asyncio.sleep(10)

        logger.info("=== Orthodox Harvester Complete! Total Forwarded: %d books ===", self.stats["forwarded"])
        self.is_running = False

orthodox_harvester = OrthodoxHarvester()
