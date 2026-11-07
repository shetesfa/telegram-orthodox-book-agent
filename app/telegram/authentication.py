from typing import Dict, Any, Optional
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    PhoneNumberInvalidError,
    PhoneCodeExpiredError
)
from app.telegram.client import telegram_manager
from app.database import update_setting
from app.config import logger

async def start_authentication(api_id: int, api_hash: str, phone: str) -> Dict[str, Any]:
    """Start login flow by sending code to phone."""
    # Store settings in DB for convenience
    await update_setting("telegram_api_id", str(api_id))
    await update_setting("telegram_api_hash", api_hash)
    await update_setting("telegram_phone", phone)

    await telegram_manager.init_client(api_id=api_id, api_hash=api_hash, phone=phone)
    client = telegram_manager.client
    if not client:
        return {"success": False, "error": "Failed to create Telegram client"}

    if not client.is_connected():
        await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        telegram_manager.state = "connected"
        telegram_manager.user_info = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username
        }
        return {"success": True, "status": "already_authorized", "user": telegram_manager.user_info}

    try:
        sent_code = await client.send_code_request(phone)
        telegram_manager.phone_code_hash = sent_code.phone_code_hash
        telegram_manager.state = "awaiting_code"
        logger.info("Telegram code sent successfully to registered phone.")
        return {"success": True, "status": "code_sent"}
    except PhoneNumberInvalidError:
        logger.error("Invalid phone number provided.")
        return {"success": False, "error": "Invalid phone number format. Please include country code (+...)."}
    except Exception as e:
        logger.error("Error sending Telegram login code: %s", type(e).__name__)
        return {"success": False, "error": str(e)}

async def submit_code(code: str) -> Dict[str, Any]:
    """Submit received SMS or Telegram login code."""
    client = telegram_manager.client
    if not client or not client.is_connected():
        return {"success": False, "error": "Telegram client not connected"}

    if not telegram_manager.phone or not telegram_manager.phone_code_hash:
        return {"success": False, "error": "No pending code request. Please restart connection."}

    try:
        await client.sign_in(
            phone=telegram_manager.phone,
            code=code.strip(),
            phone_code_hash=telegram_manager.phone_code_hash
        )
        me = await client.get_me()
        telegram_manager.state = "connected"
        telegram_manager.user_info = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username
        }
        logger.info("Telegram authentication successful for user: %s", me.id)
        return {"success": True, "status": "authorized", "user": telegram_manager.user_info}
    except SessionPasswordNeededError:
        telegram_manager.state = "awaiting_password"
        logger.info("Two-Factor Authentication (2FA) password required.")
        return {"success": True, "status": "password_needed"}
    except PhoneCodeInvalidError:
        return {"success": False, "error": "The verification code is incorrect."}
    except PhoneCodeExpiredError:
        return {"success": False, "error": "The verification code has expired. Please request a new one."}
    except Exception as e:
        logger.error("Authentication error: %s", type(e).__name__)
        return {"success": False, "error": str(e)}

async def submit_password(password: str) -> Dict[str, Any]:
    """Submit 2FA password."""
    client = telegram_manager.client
    if not client or not client.is_connected():
        return {"success": False, "error": "Telegram client not connected"}

    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        telegram_manager.state = "connected"
        telegram_manager.user_info = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username
        }
        logger.info("Two-Factor Authentication successful for user: %s", me.id)
        return {"success": True, "status": "authorized", "user": telegram_manager.user_info}
    except PasswordHashInvalidError:
        return {"success": False, "error": "Invalid 2FA password."}
    except Exception as e:
        logger.error("2FA error: %s", type(e).__name__)
        return {"success": False, "error": str(e)}

async def disconnect_telegram() -> Dict[str, Any]:
    """Disconnect user session."""
    await telegram_manager.disconnect()
    return {"success": True, "status": "disconnected"}
