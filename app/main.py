import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.config import BASE_DIR, logger
from app.database import init_db
from app.telegram.client import telegram_manager
from app.api.routes import router as api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Telegram Book Search Agent...")
    await init_db()
    try:
        # Try to auto-connect if credentials exist in .env or settings
        await telegram_manager.init_client()
        if telegram_manager.client and telegram_manager.client.is_connected():
            from app.telegram.bot_listener import telegram_book_listener
            telegram_book_listener.register()
    except Exception as e:
        logger.warning("Auto-connection to Telegram on startup deferred: %s", e)
    
    yield
    
    # Shutdown
    logger.info("Shutting down Telegram Book Search Agent...")
    await telegram_manager.disconnect()

app = FastAPI(
    title="Telegram Book Search Agent",
    description="Official-API powered personal Telegram book search and Saved Messages collector.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router)

# Serve Frontend static assets
frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    logger.warning("Frontend directory not found at: %s", frontend_dir)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
