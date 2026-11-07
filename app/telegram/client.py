import asyncio
from typing import Optional, Dict, Any
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    PhoneNumberInvalidError
)
from app.config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_PHONE,
    SESSION_PATH,
    logger
)
from app.database import update_setting, get_settings

class TelegramManager:
    _instance: Optional["TelegramManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramManager, cls).__new__(cls)
            cls._instance.client: Optional[TelegramClient] = None
            cls._instance.api_id: Optional[int] = None
            cls._instance.api_hash: str = ""
            cls._instance.phone: str = ""
            cls._instance.phone_code_hash: Optional[str] = None
            cls._instance.state: str = "disconnected"  # disconnected, awaiting_code, awaiting_password, connected
            cls._instance.user_info: Dict[str, Any] = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def init_client(self, api_id: Optional[int] = None, api_hash: str = "", phone: str = ""):
        """Initialize TelegramClient with provided or env credentials."""
        async with self._lock:
            # Check DB settings for overrides if env empty
            settings = await get_settings()
            self.api_id = api_id or (int(TELEGRAM_API_ID) if TELEGRAM_API_ID.isdigit() else None) or settings.get("telegram_api_id")
            if self.api_id:
                try:
                    self.api_id = int(self.api_id)
                except ValueError:
                    self.api_id = None

            self.api_hash = api_hash or TELEGRAM_API_HASH or settings.get("telegram_api_hash", "")
            self.phone = phone or TELEGRAM_PHONE or settings.get("telegram_phone", "")

            if not self.api_id or not self.api_hash:
                self.state = "not_configured"
                logger.info("Telegram API ID or Hash not configured yet.")
                return

            if self.client and self.client.is_connected():
                if await self.client.is_user_authorized():
                    self.state = "connected"
                    me = await self.client.get_me()
                    self.user_info = {
                        "id": me.id,
                        "first_name": me.first_name,
                        "last_name": me.last_name,
                        "username": me.username,
                        "phone": me.phone
                    }
                    return

            # Re-instantiate client with infinite retries on network drop
            self.client = TelegramClient(
                str(SESSION_PATH),
                self.api_id,
                self.api_hash,
                connection_retries=None,  # Infinite retries
                retry_delay=5,
                auto_reconnect=True,
                timeout=30
            )
            await self.client.connect()

            if await self.client.is_user_authorized():
                self.state = "connected"
                me = await self.client.get_me()
                self.user_info = {
                    "id": me.id,
                    "first_name": me.first_name,
                    "last_name": me.last_name,
                    "username": me.username,
                    "phone": me.phone
                }
                logger.info("Telegram client successfully connected and authorized as user: %s", me.id)
                try:
                    from app.telegram.bot_listener import telegram_book_listener
                    telegram_book_listener.register()
                except Exception as ble:
                    logger.warning("Could not register Telegram book listener: %s", ble)
            else:
                self.state = "disconnected"
                logger.info("Telegram client connected but user is not authorized yet.")

    async def get_status(self) -> Dict[str, Any]:
        """Returns current connection and authorization status."""
        is_conn = bool(self.client and self.client.is_connected())
        is_auth = False
        if is_conn:
            try:
                is_auth = await self.client.is_user_authorized()
            except Exception:
                is_auth = False

        if is_auth:
            self.state = "connected"
        elif self.state not in ("awaiting_code", "awaiting_password"):
            self.state = "disconnected" if (self.api_id and self.api_hash) else "not_configured"

        phone_str = str(self.phone or "")
        return {
            "state": self.state,
            "is_connected": is_conn,
            "is_authorized": is_auth,
            "phone": phone_str[:4] + "***" + phone_str[-2:] if len(phone_str) > 6 else phone_str,
            "user": self.user_info if is_auth else None,
            "has_credentials": bool(self.api_id and self.api_hash)
        }

    async def disconnect(self):
        """Disconnect client without deleting session unless requested."""
        async with self._lock:
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception as e:
                    logger.warning("Error disconnecting Telegram client: %s", e)
            self.state = "disconnected"
            self.user_info = {}
            logger.info("Telegram client disconnected.")

telegram_manager = TelegramManager()
