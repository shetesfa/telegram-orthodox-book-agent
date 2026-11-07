# የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጻሕፍት ፍለጋ እና ማሰባሰቢያ ወኪል
## Ethiopian Orthodox Tewahedo Church Spiritual Book Search & Harvester Agent

ይህ ፕሮጀክት ይፋዊውን የቴሌግራም ኤፒአይ (Telethon) እና የጉግል ጀሚኒ ሰው ሰራሽ አስተውሎትን (Google Gemini AI) በማጣመር የተገነባ፣ ለኢትዮጵያ ኦርቶዶክስ ተዋሕዶ ቤተክርስቲያን መንፈሳዊ መጻሕፍት ብቻ የተዘጋጀ ብልህ የመጽሐፍት ፍለጋ እና ማሰባሰቢያ ስርዓት ነው።

---

### ✨ ዋና ዋና ገጽታዎች (Features)

1. **🤖 በ Gemini AI የታጠቀ ጥብቅ የይዘት ማጣሪያ (Gemini AI Content Gatekeeper)**:
   - ማንኛውም የገባ የፍለጋ ጥያቄ ወይም የሚሰበሰብ መጽሐፍ 100% የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ ሰነድ መሆኑን በቅጽበት ይመረምራል።
   - ዓለማዊ መጻሕፍትን፣ ልብወለዶችን (Fictions)፣ እና የትምህርት ቤት መማሪያዎችን ወዲያውኑ ለይቶ ያግዳል፤ ምክንያቱንም በግልጽ ያብራራል።

2. **⚡ እጅግ ፈጣን የመጽሐፍት ፍለጋ (Instant Search Engine)**:
   - የአማርኛ ሆሞፎን ፊደላት ኖርማላይዜሽን (ሀ/ሐ/ኀ፣ ሰ/ሠ፣ አ/ዐ፣ ጸ/ፀ ወዘተ)።
   - ፍጹም የሆነ የተዛምዶ ደረጃ አሰጣጥ ህግ (Bulletproof Ranking Engine) - ትክክለኛው መጽሐፍ ሁልጊዜም 100% Exact Match አግኝቶ አንደኛ ይሆናል።
   - In-Memory Microsecond Caching በ 0.001 ሰከንድ ውስጥ ምላሽ ይሰጣል።

3. **📱 በቴሌግራም ግሩፕ ውስጥ በቀጥታ የሚሰራ ቦት (Group Bot Listener)**:
   - በአድሚን ግሩፕ ውስጥ በትእዛዝ ይሰራል፡
     - `@መጽሃፍ [ስም]`
     - `@መጽሐፍ [ስም]`
     - `.መጽሃፍ [ስም]`
   - ንጹሕ ፒዲኤፉን ያለ ምንም የውጭ ማስታወቂያ ወይም የውጭ forward በቀጥታ ያቀርባል።

4. **🏛 ይፋዊ ማኅተም (Official Sunday School Caption)**:
   - እያንዳንዱ ፒዲኤፍ ሲላክ በውስጡ የሚያምር ማኅተም ይኖረዋል፦
     - *ርዕስ:* **[የመጽሐፉ ስም]**
     - *ፋይል:* [ፋይል.pdf]
     - `our telegram channel` (ጠቅ ሲደረግ ቻናሉን የሚከፍት ንቁ ሊንክ)
     - **አጸደ ትጉሃን ሰንበት ትምህርት ቤት**
     - **Atsede tguhan sunday school**

5. **🌐 ዘመናዊ የድር መቆጣጠሪያ ዳሽቦርድ (Web UI Dashboard)**:
   - FastAPI እና ንጹሕ HTML5/CSS3/Vanilla JS የተገነባ።
   - የቀጥታ ፍለጋ፣ የሂደት መከታተያ እና የ Gemini AI ማረጋገጫ ገጽ።

---

### 🚀 አጠቃቀም እና አጫጫን (Installation & Setup)

1. **ኮዱን ያውርዱ (Clone repository)**:
   ```bash
   git clone https://github.com/<username>/<repo-name>.git
   cd telegram-book-agent
   ```

2. **አስፈላጊ ፓኬጆችን ይጫኑ (Install dependencies)**:
   ```bash
   pip install -r requirements.txt
   ```

3. **የአካባቢ ተለዋዋጮችን ያዋቅሩ (.env Configuration)**:
   - `.env.example` ፋይሉን ወደ `.env` ይቀይሩ፡
   ```bash
   cp .env.example .env
   ```
   - የቴሌግራም ኤፒአይ (`API_ID`, `API_HASH`) ከ https://my.telegram.org ያምጡ።
   - ነጻ Gemini API Key ከ https://aistudio.google.com ያምጡ።

4. **ሰርቨሩን ያስነሱ (Run Server)**:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```
   - ዳሽቦርዱን በ `http://localhost:8080` ይክፈቱ።

---

### 📜 ፈቃድ (License)
ይህ ፕሮጀክት ለአጸደ ትጉሃን ሰንበት ትምህርት ቤት እና ለኢትዮጵያ ኦርቶዶክስ ተዋሕዶ ምእመናን አገልግሎት በክብር የተዘጋጀ ነው።
