import asyncio
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Fix Windows console UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from app.database import init_db, add_book, get_all_books, clear_all_books
from app.config import logger

DOCX_PATH = Path(r"E:\users\documents\new ook\የቤተመጽሐፍት_መጽሐፍትን_መመዝገቢያ_ቅጽ.docx")

async def extract_and_import():
    if not DOCX_PATH.exists():
        print(f"Error: File not found at {DOCX_PATH}")
        return

    print(f"Reading document: {DOCX_PATH}...")
    await init_db()

    z = zipfile.ZipFile(DOCX_PATH)
    root = ET.fromstring(z.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    extracted_books = []
    
    # Iterate over table rows
    for tr in root.findall(".//w:tr", ns):
        cells = tr.findall(".//w:tc", ns)
        row_text = []
        for tc in cells:
            texts = [t.text for t in tc.findall(".//w:t", ns) if t.text]
            row_text.append("".join(texts).strip())

        if len(row_text) >= 2:
            # Expected columns:
            # 0: ተ.ቁ, 1: የመጽሐፉ ስም, 2: የመጽሐፉ ጸሐፊ ስም, 3: ዓመተምህረት, 4: ብዛት, 5: ዋጋ, 6: ማተሚያ ቤት, 7: ኮድ
            title = row_text[1] if len(row_text) > 1 else ""
            author = row_text[2] if len(row_text) > 2 else ""
            year = row_text[3] if len(row_text) > 3 else ""

            # Skip header or empty rows
            if not title or title in ("የመጽሐፉ ስም", "ተ.ቁ"):
                continue

            extracted_books.append({
                "title": title,
                "author": author,
                "edition": year,
                "isbn": ""
            })

    print(f"Extracted {len(extracted_books)} valid book titles from docx table.")

    # Import into Database
    added_count = 0
    for b in extracted_books:
        await add_book(
            title=b["title"],
            author=b["author"],
            edition=b["edition"],
            isbn=b["isbn"]
        )
        added_count += 1

    total_in_db = len(await get_all_books())
    print(f"Successfully imported {added_count} books into the app database!")
    print(f"Total books in app queue: {total_in_db}")

if __name__ == "__main__":
    asyncio.run(extract_and_import())
