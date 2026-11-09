import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.database import (
    get_all_books,
    update_book_status,
    get_settings,
    is_file_processed
)
from app.telegram.client import telegram_manager
from app.telegram.search import search_documents_in_sources
from app.telegram.sender import send_book_to_saved_messages
from app.books.matcher import rank_candidates
from app.books.gemini_verifier import ensure_book_verified_before_output
from app.books.classifier import classify_book_locally
from app.config import logger

class BatchProcessor:
    _instance: Optional["BatchProcessor"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BatchProcessor, cls).__new__(cls)
            cls._instance.is_running = False
            cls._instance.is_paused = False
            cls._instance._stop_requested = False
            cls._instance._pause_event = asyncio.Event()
            cls._instance._pause_event.set()  # Initially unpaused
            cls._instance.current_task: Optional[asyncio.Task] = None
            
            # Progress and stats
            cls._instance.total_books = 0
            cls._instance.current_index = 0
            cls._instance.current_title = ""
            cls._instance.stats = {
                "requested": 0,
                "found": 0,
                "sent": 0,
                "not_found": 0,
                "needs_review": 0,
                "failed": 0,
                "skipped_duplicates": 0
            }
            cls._instance.pending_reviews: List[Dict[str, Any]] = []
        return cls._instance

    def get_progress(self) -> Dict[str, Any]:
        """Get live status and statistics."""
        percent = 0.0
        if self.total_books > 0:
            percent = round((self.current_index / self.total_books) * 100, 1)

        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "current_index": self.current_index,
            "total_books": self.total_books,
            "current_title": self.current_title,
            "progress_percent": percent,
            "stats": self.stats,
            "pending_reviews_count": len(self.pending_reviews)
        }

    async def start(self):
        """Start or restart the batch search task."""
        if self.is_running:
            return {"success": False, "message": "Batch search is already running"}

        self.is_running = True
        self.is_paused = False
        self._stop_requested = False
        self._pause_event.set()
        self.current_task = asyncio.create_task(self._process_loop())
        return {"success": True, "message": "Batch search started"}

    def pause(self):
        """Pause running batch search."""
        if not self.is_running or self.is_paused:
            return {"success": False, "message": "Not running or already paused"}
        self.is_paused = True
        self._pause_event.clear()
        logger.info("Batch search paused by user.")
        return {"success": True, "message": "Batch search paused"}

    def resume(self):
        """Resume paused batch search."""
        if not self.is_running or not self.is_paused:
            return {"success": False, "message": "Not paused"}
        self.is_paused = False
        self._pause_event.set()
        logger.info("Batch search resumed by user.")
        return {"success": True, "message": "Batch search resumed"}

    async def stop(self):
        """Stop running batch search."""
        if not self.is_running:
            return {"success": False, "message": "Batch search not running"}
        self._stop_requested = True
        self.is_paused = False
        self._pause_event.set()  # Unblock if waiting
        if self.current_task:
            self.current_task.cancel()
        self.is_running = False
        logger.info("Batch search stopped by user.")
        return {"success": True, "message": "Batch search stopped"}

    async def _process_loop(self):
        """Internal asynchronous loop over pending books."""
        try:
            settings = await get_settings()
            min_conf = float(settings.get("min_confidence", 90.0))
            review_thresh = float(settings.get("review_threshold", 70.0))
            auto_send = settings.get("auto_send_high_confidence", True)
            ask_uncertain = settings.get("ask_uncertain", True)
            continue_on_err = settings.get("continue_after_errors", True)

            weights = {
                "title": float(settings.get("weight_title", 60.0)),
                "author": float(settings.get("weight_author", 25.0)),
                "edition": float(settings.get("weight_edition", 10.0)),
                "relevance": float(settings.get("weight_relevance", 5.0))
            }

            all_books = await get_all_books()
            # Process pending, searching, or if none pending, retry not_found/failed
            books_to_process = [b for b in all_books if b["status"] in ("pending", "searching")]
            if not books_to_process:
                books_to_process = [b for b in all_books if b["status"] in ("not_found", "failed")]
            self.total_books = len(books_to_process)
            self.current_index = 0
            self.stats = {
                "requested": len(all_books),
                "found": 0,
                "sent": 0,
                "not_found": 0,
                "needs_review": 0,
                "failed": 0,
                "skipped_duplicates": 0
            }
            self.pending_reviews.clear()

            logger.info("Starting batch processing of %d books.", self.total_books)

            for idx, book in enumerate(books_to_process, 1):
                if self._stop_requested:
                    break

                # Handle pause
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                self.current_index = idx
                self.current_title = book["title"]
                book_id = book["id"]

                # 0. Pre-Scan: Block stale fiction/academic titles sitting in DB in 0.001s
                local_check = classify_book_locally(title=book["title"])
                if local_check["category"] in ("Fiction", "Scientific/Academic", "Other_Religion", "Secular"):
                    logger.warning("🛑 [Batch Processor] Blocked blacklisted entry '%s' (%s)", book["title"], local_check["reason"])
                    self.stats["failed"] += 1
                    await update_book_status(
                        book_id,
                        status="rejected",
                        is_orthodox=False,
                        verified_by="rejected",
                        verification_score=0.0,
                        book_category=local_check["category"],
                        verification_reason=local_check["reason"],
                        notes=f"Rejected: {local_check['reason']}"
                    )
                    continue

                await update_book_status(book_id, "searching")
                logger.info("[%d/%d] Searching for: %s", idx, self.total_books, book["title"])

                try:
                    # 1. Search in authorized Telegram sources
                    candidates = await search_documents_in_sources(book["title"])
                    if not candidates:
                        self.stats["not_found"] += 1
                        await update_book_status(book_id, "not_found", notes="No matching documents found in sources")
                        logger.info("❌ Not found: %s", book["title"])
                        continue

                    # 2. Score candidates
                    ranked = rank_candidates(
                        candidates,
                        requested_title=book["title"],
                        author=book.get("author", ""),
                        edition=book.get("edition", ""),
                        weights=weights
                    )
                    best_candidate = ranked[0]
                    best_score = best_candidate["confidence"]
                    logger.info("Best candidate for '%s': %s (Confidence: %s%%)", book["title"], best_candidate["filename"], best_score)

                    self.stats["found"] += 1

                    # 3. Decision based on score
                    if best_score >= min_conf:
                        if auto_send:
                            logger.info("Confidence >= %s%% (got %s%%). Sending automatically to Saved Messages...", min_conf, best_score)
                            send_res = await send_book_to_saved_messages(
                                best_candidate,
                                requested_title=book["title"],
                                author=book.get("author", ""),
                                confidence=best_score,
                                book_id=book_id
                            )
                            if send_res.get("status") == "duplicate_skipped":
                                self.stats["skipped_duplicates"] += 1
                                await update_book_status(book_id, "sent", confidence=best_score, selected_file=best_candidate["filename"], notes="Duplicate skipped (already sent previously)")
                            elif send_res.get("status") == "rejected":
                                self.stats["failed"] += 1
                                await update_book_status(book_id, "rejected", confidence=0.0, notes=send_res.get("error", "Rejected by verification gate"))
                            elif send_res.get("success"):
                                self.stats["sent"] += 1
                                await update_book_status(book_id, "sent", confidence=best_score, selected_file=best_candidate["filename"])
                            else:
                                self.stats["failed"] += 1
                                await update_book_status(book_id, "failed", confidence=best_score, notes=send_res.get("error", "Send error"))
                        else:
                            # Auto-send disabled, mark as found
                            await update_book_status(book_id, "found", confidence=best_score, selected_file=best_candidate["filename"])

                    elif best_score >= review_thresh:
                        if ask_uncertain:
                            self.stats["needs_review"] += 1
                            review_entry = {
                                "book_id": book_id,
                                "requested_title": book["title"],
                                "candidates": ranked[:5]
                            }
                            self.pending_reviews.append(review_entry)
                            await update_book_status(book_id, "review_required", confidence=best_score, selected_file=best_candidate["filename"], notes="Confidence requires user review")
                            logger.info("⚠️ Needs review for '%s' (Confidence: %s%%)", book["title"], best_score)
                        else:
                            self.stats["not_found"] += 1
                            await update_book_status(book_id, "not_found", confidence=best_score, notes="Confidence below auto threshold")

                    else:
                        self.stats["not_found"] += 1
                        await update_book_status(book_id, "not_found", confidence=best_score, notes="Confidence too low")
                        logger.info("❌ Low confidence (%s%%): %s", best_score, book["title"])

                except Exception as book_err:
                    logger.error("Error processing book '%s': %s", book["title"], book_err)
                    self.stats["failed"] += 1
                    await update_book_status(book_id, "failed", notes=str(book_err))
                    if not continue_on_err:
                        logger.error("Stopping batch due to error and continue_after_errors=False.")
                        break

                # Slight throttle to be polite to Telegram API limits
                await asyncio.sleep(1.0)

            logger.info("Batch processing finished.")
        except asyncio.CancelledError:
            logger.info("Batch processing cancelled.")
        except Exception as e:
            logger.error("Unhandled batch processor error: %s", e)
        finally:
            self.is_running = False
            self.is_paused = False

batch_processor = BatchProcessor()
