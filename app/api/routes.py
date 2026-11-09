import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Header, Depends
from pydantic import BaseModel

from app.database import (
    get_all_books,
    add_book,
    delete_book,
    clear_all_books,
    get_all_sources,
    set_source_enabled,
    get_processed_history,
    get_settings,
    update_setting
)
from app.telegram.client import telegram_manager
from app.telegram.authentication import (
    start_authentication,
    submit_code,
    submit_password,
    disconnect_telegram
)
from app.telegram.search import (
    discover_telegram_sources,
    search_documents_in_sources
)
from app.telegram.sender import send_book_to_saved_messages
from app.books.parser import (
    parse_book_string,
    parse_txt_content,
    parse_csv_content
)
from app.books.matcher import rank_candidates
from app.books.processor import batch_processor
from app.telegram.harvester import orthodox_harvester
from app.config import LOG_FILE, ADMIN_API_KEY, logger

router = APIRouter(prefix="/api")

def verify_admin_key(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")):
    """Security check: requires valid X-Admin-Key header if ADMIN_API_KEY is configured."""
    from app import config
    key = config.ADMIN_API_KEY or os.getenv("ADMIN_API_KEY", "").strip()
    if key:
        if not x_admin_key or x_admin_key.strip() != key:
            raise HTTPException(
                status_code=403,
                detail="የአድሚን ፈቃድ የለዎትም (Unauthorized: Invalid or missing X-Admin-Key)"
            )

# Models
class TelegramConnectRequest(BaseModel):
    api_id: int
    api_hash: str
    phone: str

class TelegramCodeRequest(BaseModel):
    code: str

class TelegramPasswordRequest(BaseModel):
    password: str

class BookCreateRequest(BaseModel):
    title: str
    author: Optional[str] = ""
    isbn: Optional[str] = ""
    edition: Optional[str] = ""

class BooksBatchAddRequest(BaseModel):
    text: str  # multiple titles separated by newlines

class SourceToggleRequest(BaseModel):
    chat_id: int
    enabled: bool

class SearchTestRequest(BaseModel):
    title: str
    author: Optional[str] = ""
    edition: Optional[str] = ""

class SendFileRequest(BaseModel):
    candidate: Dict[str, Any]
    requested_title: str
    author: Optional[str] = ""
    confidence: float
    force_resend: Optional[bool] = False

class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]

# --- 1. Telegram Connection & Auth ---
@router.get("/telegram/status")
async def get_tg_status():
    return await telegram_manager.get_status()

@router.post("/telegram/connect")
async def connect_tg(req: TelegramConnectRequest):
    res = await start_authentication(req.api_id, req.api_hash, req.phone)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Connection error"))
    return res

@router.post("/telegram/submit-code")
async def submit_tg_code(req: TelegramCodeRequest):
    res = await submit_code(req.code)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Invalid code"))
    return res

@router.post("/telegram/submit-password")
async def submit_tg_password(req: TelegramPasswordRequest):
    res = await submit_password(req.password)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Invalid password"))
    return res

@router.post("/telegram/disconnect", dependencies=[Depends(verify_admin_key)])
async def disconnect_tg():
    return await disconnect_telegram()

# --- 2. Telegram Sources ---
@router.get("/telegram/sources")
async def list_sources():
    sources = await get_all_sources()
    return sources

@router.post("/telegram/sources/discover")
async def discover_sources():
    sources = await discover_telegram_sources()
    return sources

@router.post("/telegram/sources/toggle")
async def toggle_source(req: SourceToggleRequest):
    await set_source_enabled(req.chat_id, req.enabled)
    return {"success": True, "chat_id": req.chat_id, "enabled": req.enabled}

# --- 3. Books Management ---
@router.get("/books")
async def get_books(all_statuses: bool = False):
    """Returns books. By default returns only verified Orthodox books (is_orthodox = 1)."""
    return await get_all_books(only_orthodox=not all_statuses)

@router.post("/books")
async def create_book(req: BookCreateRequest):
    book_id = await add_book(req.title, req.author or "", req.isbn or "", req.edition or "")
    return {"success": True, "id": book_id}

@router.post("/books/batch-text")
async def add_books_batch(req: BooksBatchAddRequest):
    parsed = parse_txt_content(req.text)
    added_ids = []
    for b in parsed:
        bid = await add_book(b["title"], b.get("author", ""), b.get("isbn", ""), b.get("edition", ""))
        added_ids.append(bid)
    return {"success": True, "count": len(added_ids)}

@router.post("/books/import")
async def import_books_file(file: UploadFile = File(...)):
    contents = (await file.read()).decode("utf-8", errors="ignore")
    fname = file.filename.lower()
    if fname.endswith(".csv"):
        parsed = parse_csv_content(contents)
    else:
        parsed = parse_txt_content(contents)

    added_ids = []
    for b in parsed:
        bid = await add_book(b["title"], b.get("author", ""), b.get("isbn", ""), b.get("edition", ""))
        added_ids.append(bid)
    return {"success": True, "count": len(added_ids)}

@router.delete("/books/{book_id}", dependencies=[Depends(verify_admin_key)])
async def remove_book(book_id: int):
    await delete_book(book_id)
    return {"success": True}

@router.delete("/books", dependencies=[Depends(verify_admin_key)])
@router.delete("/books/clear-all", dependencies=[Depends(verify_admin_key)])
async def remove_all_books():
    await clear_all_books()
    return {"success": True}

# --- 4. Search & Test Mode ---
@router.post("/search/test")
async def test_search(req: SearchTestRequest):
    # 1. Search files
    candidates = await search_documents_in_sources(req.title)
    if not candidates:
        return {"candidates": []}

    # 2. Score candidates
    settings = await get_settings()
    weights = {
        "title": float(settings.get("weight_title", 60.0)),
        "author": float(settings.get("weight_author", 25.0)),
        "edition": float(settings.get("weight_edition", 10.0)),
        "relevance": float(settings.get("weight_relevance", 5.0))
    }
    ranked = rank_candidates(
        candidates,
        requested_title=req.title,
        author=req.author or "",
        edition=req.edition or "",
        weights=weights
    )
    return {"candidates": ranked}

@router.post("/search/send")
async def send_file_endpoint(req: SendFileRequest):
    res = await send_book_to_saved_messages(
        candidate=req.candidate,
        requested_title=req.requested_title,
        author=req.author or "",
        confidence=req.confidence,
        force_resend=req.force_resend or False
    )
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "Failed to send"))
    return res

# --- 5. Batch Automation ---
@router.post("/batch/start")
async def start_batch():
    return await batch_processor.start()

@router.post("/batch/pause")
def pause_batch():
    return batch_processor.pause()

@router.post("/batch/resume")
def resume_batch():
    return batch_processor.resume()

@router.post("/batch/stop")
async def stop_batch():
    return await batch_processor.stop()

@router.get("/batch/status")
def batch_status():
    return batch_processor.get_progress()

# --- 6. History & Logs ---
@router.get("/history")
async def history_list(status: Optional[str] = None):
    return await get_processed_history(status)

@router.get("/logs")
def get_recent_logs(lines: int = 100):
    if not os.path.exists(LOG_FILE):
        return {"logs": []}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            return {"logs": [line.strip() for line in all_lines[-lines:]]}
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"]}

# --- 7. Settings ---
@router.get("/settings")
async def get_all_settings():
    return await get_settings()

@router.post("/settings", dependencies=[Depends(verify_admin_key)])
async def save_settings(req: SettingsUpdateRequest):
    for k, v in req.settings.items():
        await update_setting(k, v)
    return {"success": True, "settings": await get_settings()}

# --- 8. Orthodox Harvester Automation ---
@router.post("/orthodox/start")
async def start_orthodox_harvester():
    return await orthodox_harvester.start()

@router.post("/orthodox/stop")
def stop_orthodox_harvester():
    return orthodox_harvester.stop()

@router.get("/orthodox/status")
def get_orthodox_harvester_status():
    return orthodox_harvester.get_status()

@router.post("/orthodox/delete-fictions", dependencies=[Depends(verify_admin_key)])
async def delete_orthodox_fictions():
    return await orthodox_harvester.delete_fictions_from_channel()

# --- 9. Smart Book Search Engine ---
@router.get("/search")
@router.get("/books/search")
async def search_books_endpoint(q: str, limit: int = 10):
    from app.books.search_engine import search_books_in_db
    results = await search_books_in_db(q, limit=limit)
    # Ensure only verified Orthodox books (filter out any non-orthodox)
    verified_results = [r for r in results if r.get("score", 0.0) >= 0.50]
    return {"query": q, "total_found": len(verified_results), "results": verified_results}

@router.get("/books/search-global")
async def search_books_global_endpoint(q: str, limit: int = 5):
    from app.books.search_engine import search_books_global
    client = telegram_manager.client
    if not client or not client.is_connected():
        return {"error": "Telegram client not connected"}
    results = await search_books_global(client, q, limit=limit)
    # Filter out raw msg_obj for clean JSON serialization
    clean_results = []
    for r in results:
        clean_results.append({
            "title": r["title"],
            "filename": r["filename"],
            "source": r["source"],
            "category": r["category"],
            "file_size": r["file_size"],
            "score": r["score"]
        })
    return {"query": q, "total_found": len(clean_results), "results": clean_results}

# --- 10. Gemini AI Book Verification ---
@router.get("/books/verify-gemini")
async def verify_gemini_endpoint(title: str, caption: str = ""):
    from app.books.gemini_verifier import verify_book_with_gemini
    res = await verify_book_with_gemini(filename=title, caption=caption)
    return res


