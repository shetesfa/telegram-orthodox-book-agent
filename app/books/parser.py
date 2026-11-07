import re
import csv
import io
from typing import Dict, Any, List, Optional

def normalize_text(text: str) -> str:
    """Normalize text by lowercasing, replacing punctuation with spaces, and trimming."""
    if not text:
        return ""
    # Remove file extensions like .pdf, .epub
    text = re.sub(r"\.(pdf|epub|mobi|djvu|docx?)$", "", text, flags=re.IGNORECASE)
    # Replace separators (_, -, ., +, [, ], (, )) with spaces
    text = re.sub(r"[_\-\.\+\[\]\(\)\{\},]", " ", text)
    # Normalize multiple whitespace
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text

def extract_edition(text: str) -> Optional[str]:
    """Extract edition information (e.g., '8th edition', '8e', '2nd ed')."""
    if not text:
        return None
    patterns = [
        r"(\d+)(?:st|nd|rd|th)?\s*(?:edition|ed\b|e\b)",
        r"(?:edition|ed\b)\s*(\d+)",
        r"\bv(\d+)\b"
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def extract_year(text: str) -> Optional[str]:
    """Extract 4-digit release year (e.g. 1990-2030)."""
    if not text:
        return None
    m = re.search(r"\b(19\d{2}|20[0-3]\d)\b", text)
    return m.group(1) if m else None

def parse_book_string(raw: str) -> Dict[str, Any]:
    """Parse a single raw book entry string."""
    clean = raw.strip()
    edition = extract_edition(clean) or ""
    year = extract_year(clean) or ""
    
    # Check if author is formatted with 'by' or '-'
    author = ""
    title = clean
    if " by " in clean.lower():
        parts = re.split(r"\s+by\s+", clean, flags=re.IGNORECASE, maxsplit=1)
        title, author = parts[0].strip(), parts[1].strip()
    elif " - " in clean:
        parts = clean.split(" - ", 1)
        title, author = parts[0].strip(), parts[1].strip()

    return {
        "title": title,
        "author": author,
        "edition": edition,
        "year": year,
        "isbn": ""
    }

def parse_txt_content(content: str) -> List[Dict[str, Any]]:
    """Parse plain text book list (one title per line)."""
    books = []
    lines = content.strip().splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parsed = parse_book_string(line)
        if parsed["title"]:
            books.append(parsed)
    return books

def parse_csv_content(content: str) -> List[Dict[str, Any]]:
    """Parse CSV book list (title, author, isbn, edition)."""
    books = []
    f = io.StringIO(content.strip())
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        return books

    # Normalize fieldnames to lowercase
    fieldnames = [fn.strip().lower() for fn in reader.fieldnames]
    
    for row in reader:
        # Match case-insensitively
        norm_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
        title = norm_row.get("title", "")
        if not title:
            continue
        raw_edition = norm_row.get("edition", "")
        clean_edition = extract_edition(raw_edition) or extract_edition(title) or raw_edition
        books.append({
            "title": title,
            "author": norm_row.get("author", ""),
            "isbn": norm_row.get("isbn", ""),
            "edition": clean_edition
        })
    return books
