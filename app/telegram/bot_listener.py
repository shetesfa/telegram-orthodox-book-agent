import re
import asyncio
from typing import Optional
from telethon import events
from telethon.tl.types import DocumentAttributeFilename
from app.config import logger
from app.telegram.client import telegram_manager
from app.books.search_engine import search_books_in_db, search_books_global, normalize_amharic, is_definitely_fiction_or_secular
from app.books.gemini_verifier import verify_book_with_gemini
from app.telegram.harvester import TARGET_CHANNEL_LINK

TRIGGER_PREFIXES = [
    "@መጽሃፍ", "@መጽሐፍ",
    ".መጽሃፍ", ".መጽሐፍ",
    "!መጽሃፍ", "!መጽሐፍ",
    "/find", "/book", "/search"
]

OUR_CHANNEL_TAG = "@atsedeteguhan"
OUR_CHANNEL_LINK = "https://t.me/atsedeteguhan"

def format_clean_pdf_caption(title: str, filename: str) -> str:
    """ንጹሕ እና ውብ የፒዲኤፍ መግለጫ በ HTML ቅርጸት (ምንም አይነት ያልተፈለገ _ ወይም * የሌለው)"""
    return (
        f"<i>ርዕስ:</i> <b>{title}</b>\n"
        f"<i>ፋይል:</i> {filename}\n\n"
        f'<a href="{OUR_CHANNEL_LINK}">our telegram channel</a>\n\n'
        f"<b>አጸደ ትጉሃን ሰንበት ትምህርት ቤት</b>\n"
        f"<b>Atsede tguhan sunday school</b>"
    )

class TelegramBookBotListener:
    _instance: Optional["TelegramBookBotListener"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramBookBotListener, cls).__new__(cls)
            cls._instance.is_active = False
            cls._instance._handler = None
        return cls._instance

    def register(self):
        """የቴሌግራም አድሚን ግሩፕ የመልእክት አዳማጭን ያነሳል"""
        client = telegram_manager.client
        if not client:
            logger.warning("Telegram client not available for listener registration.")
            return

        if self.is_active:
            logger.info("Telegram Book Bot Listener is already active.")
            return

        @client.on(events.NewMessage)
        async def on_new_message(event):
            try:
                raw_text = event.raw_text or ""
                if not raw_text.strip():
                    return

                matched_prefix = None
                query = ""
                for p in TRIGGER_PREFIXES:
                    if raw_text.strip().startswith(p):
                        matched_prefix = p
                        query = raw_text.strip()[len(p):].strip()
                        break

                if not matched_prefix or not query:
                    return

                logger.info("Book Search Command Received: prefix='%s', query='%s' (chat: %s)", matched_prefix, query, event.chat_id)

                # 0. ደረጃ 0፡ የተጠቃሚውን ጥያቄ በቅድሚያ ማጣራት (Pre-screening query)
                # ሀ. ፈጣን ማጣሪያ (የታወቁ ልብወለዶች እና የትምህርት ቤት መጻሕፍት)
                if is_definitely_fiction_or_secular(query, ""):
                    logger.info("🛑 Blocked secular/fiction query by fast-filter: '%s'", query)
                    await event.reply(
                        f"ይቅርታ፣ «{query}» የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጽሐፍ አይደለም።\n"
                        f"ምክንያት: ይህ ዓለማዊ/ልብወለድ ወይም የትምህርት ቤት መጽሐፍ ነው።\n\n"
                        f"እባክዎ የመንፈሳዊ መጽሐፍ ስም ጽፈው ይፈልጉ (ምሳሌ፦ @መጽሃፍ ተአምረ ማርያም)።"
                    )
                    return

                # ለ. የጥያቄውን መንፈሳዊነት በ Gemini AI ማረጋገጥ (ትክክለኛውን ምክንያት በቀጥታ ማሳወቅ)
                query_gemini = await verify_book_with_gemini(filename=query, caption="")
                if not query_gemini.get("is_orthodox", False):
                    gemini_reason = query_gemini.get("reason", "ይህ ርዕስ የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጽሐፍ አይደለም።")
                    logger.info("🛑 Gemini AI Blocked non-orthodox query: '%s' (Reason: %s)", query, gemini_reason)
                    await event.reply(
                        f"ይቅርታ፣ «{query}» የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጽሐፍ አይደለም።\n"
                        f"ምክንያት: {gemini_reason}\n\n"
                        f"እባክዎ የመንፈሳዊ መጽሐፍ ስም ጽፈው ይፈልጉ (ምሳሌ፦ @መጽሃፍ ተአምረ ማርያም ፣ @መጽሃፍ ፍትሐ ነገሥት)።"
                    )
                    return

                # 1. ደረጃ 1፡ በዳታቤዝ ውስጥ የተጠየቀውን መጽሐፍ መፈለግ
                db_results = await search_books_in_db(query, limit=5)

                if db_results:
                    best_match = db_results[0]
                    score = best_match.get("score", 0.0)

                    # ጥብቅ የተዛምዶ ማጣሪያ፡ ነጥቡ ከ 0.70 በታች ከሆነ ወይም ዋናው ቃል ካልተገኘ መጽሐፉን አይልክም!
                    q_words = set(normalize_amharic(query).split())
                    match_title_norm = normalize_amharic(best_match.get("clean_title") or best_match.get("title") or "")
                    
                    # ቢያንስ አንድ ጠቃሚ ቃል (ከ 2 ፊደል በላይ የሆነ) በውስጡ መገኘት አለበት
                    has_real_word_match = any(w in match_title_norm for w in q_words if len(w) >= 3)

                    if score >= 0.70 and has_real_word_match:
                        # በጀርባ በ Gemini AI የመጽሐፉን ይዘት ማረጋገጥ
                        gemini_check = await verify_book_with_gemini(
                            filename=best_match.get("filename", ""),
                            caption=best_match.get("title", "")
                        )

                        if not gemini_check.get("is_orthodox", False):
                            logger.warning("Gemini AI Rejected DB book: '%s' (Reason: %s)", best_match['filename'], gemini_check.get('reason'))
                            await event.reply(
                                f"ይቅርታ፣ የተገኘው ሰነድ በምርመራ የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጽሐፍ ሆኖ ስላልተገኘ አልተላከም።\n"
                                f"ምክንያት: {gemini_check.get('reason', 'መንፈሳዊ ይዘት የለውም')}"
                            )
                            return

                        # ሚዲያውን ከዋናው ምንጭ መልእክት ማምጣት
                        media_to_send = None
                        source_chat = best_match.get("telegram_chat_id")
                        source_msg_id = best_match.get("telegram_message_id")
                        if source_chat and source_msg_id:
                            try:
                                orig_msg = await client.get_messages(source_chat, ids=source_msg_id)
                                if orig_msg and orig_msg.media:
                                    media_to_send = orig_msg.media
                            except Exception as me:
                                logger.warning("Could not fetch media from source chat: %s", me)

                        if not media_to_send:
                            try:
                                our_channel = await client.get_entity(TARGET_CHANNEL_LINK)
                                async for ch_msg in client.iter_messages(our_channel, limit=30):
                                    if ch_msg.document:
                                        for attr in getattr(ch_msg.document, 'attributes', []):
                                            if isinstance(attr, DocumentAttributeFilename) and attr.file_name == best_match.get("filename"):
                                                media_to_send = ch_msg.media
                                                break
                                    if media_to_send:
                                        break
                            except Exception as ce:
                                logger.warning("Could not search our target channel: %s", ce)

                        if media_to_send:
                            actual_filename = best_match.get("filename", "")
                            if hasattr(media_to_send, 'document') and media_to_send.document:
                                for attr in getattr(media_to_send.document, 'attributes', []):
                                    if isinstance(attr, DocumentAttributeFilename):
                                        actual_filename = attr.file_name
                                        break

                            actual_title = best_match.get("clean_title") or best_match.get("title", "")
                            if not actual_title or actual_title == actual_filename:
                                actual_title = re.sub(r"\.(pdf|epub|djvu)$", "", actual_filename, flags=re.IGNORECASE).replace("_", " ").strip()

                            clean_caption = format_clean_pdf_caption(actual_title, actual_filename)

                            await client.send_file(
                                event.chat_id,
                                file=media_to_send,
                                caption=clean_caption,
                                parse_mode="html",
                                force_document=True,
                                reply_to=event.message.id
                            )
                            logger.info("Directly sent clean PDF '%s' (title: '%s') to chat %s", actual_filename, actual_title, event.chat_id)
                            return

                # 2. ደረጃ 2፡ በዳታቤዝ ካልተገኘ በቴሌግራም ግሎባል ፍለጋ መፈለግ
                status_msg = await event.reply(
                    f"«{query}» በማከማቻችን አልተገኘም። አሁን በቴሌግራም ህዝባዊ ማከማቻዎች እየተፈለገ ነው፤ ጥቂት ሰከንዶች ይጠብቁ..."
                )

                global_results = await search_books_global(client, query, limit=3)

                if global_results:
                    best_global = global_results[0]

                    # በ Gemini AI ማረጋገጥ
                    gemini_check = await verify_book_with_gemini(
                        filename=best_global.get("filename", ""),
                        caption=best_global.get("title", "")
                    )

                    if not gemini_check.get("is_orthodox", False):
                        logger.warning("Gemini AI Rejected Global result: '%s' (Reason: %s)", best_global['filename'], gemini_check.get('reason'))
                        await status_msg.edit(
                            f"በቴሌግራም ፍለጋ የተገኘው ሰነድ በምርመራ የኢትዮጵያ ኦርቶዶክስ ተዋሕዶ መንፈሳዊ መጽሐፍ አለመሆኑ ተረጋግጧል፤ ስለዚህ አልተላከም።"
                        )
                        return

                    g_msg = best_global["msg_obj"]
                    actual_filename = best_global.get("filename", "")
                    if hasattr(g_msg, 'document') and g_msg.document:
                        for attr in getattr(g_msg.document, 'attributes', []):
                            if isinstance(attr, DocumentAttributeFilename):
                                actual_filename = attr.file_name
                                break

                    actual_title = best_global.get("title", "")
                    if not actual_title or actual_title == actual_filename:
                        actual_title = re.sub(r"\.(pdf|epub|djvu)$", "", actual_filename, flags=re.IGNORECASE).replace("_", " ").strip()

                    clean_caption = format_clean_pdf_caption(actual_title, actual_filename)

                    await status_msg.delete()

                    await client.send_file(
                        event.chat_id,
                        file=g_msg.media,
                        caption=clean_caption,
                        parse_mode="html",
                        force_document=True,
                        reply_to=event.message.id
                    )
                    logger.info("Directly sent global clean PDF '%s' to chat %s", actual_filename, event.chat_id)

                    # ወደ ዒላማው ቻናላችን ማከል
                    try:
                        our_dest = await client.get_entity(TARGET_CHANNEL_LINK)
                        ch_post = await client.send_file(
                            our_dest,
                            file=g_msg.media,
                            caption=clean_caption,
                            parse_mode="html",
                            force_document=True
                        )
                        from app.database import record_processed_file
                        await record_processed_file(
                            requested_title=actual_title,
                            author="Orthodox Church",
                            source=OUR_CHANNEL_TAG,
                            telegram_chat_id=our_dest.id if hasattr(our_dest, 'id') else 0,
                            telegram_message_id=ch_post.id,
                            filename=actual_filename,
                            file_size=best_global.get("file_size", 0),
                            confidence=100.0,
                            status="sent"
                        )
                    except Exception as e:
                        logger.warning("Could not auto-archive to our channel: %s", e)

                else:
                    # 3. ደረጃ 3፡ መጽሐፉ በፍጹም ካልተገኘ የሚሰጠው አጭር ማስታወቂያ
                    not_found_response = (
                        f"ይቅርታ፣ «{query}» የተሰኘ መጽሐፍ በኦርቶዶክስ ተዋሕዶ ማከማቻችንም ሆነ በቴሌግራም ቻናሎች አልተገኘም።\n\n"
                        f"ቻናል: {OUR_CHANNEL_TAG}"
                    )
                    await status_msg.edit(not_found_response)

                    # ጥያቄው መንፈሳዊ መሆኑ ከተረጋገጠ ብቻ በማስታወሻ መመዝገብ
                    if query_gemini.get("is_orthodox", False):
                        try:
                            from app.database import add_book
                            await add_book(title=query, notes=f"Requested via group search from chat {event.chat_id}")
                        except Exception as re:
                            logger.warning("Could not record missing book: %s", re)

            except Exception as e:
                logger.error("Error processing group book command: %s", e)

        self._handler = on_new_message
        self.is_active = True
        logger.info("Telegram Book Bot Listener registered successfully. Listening for: %s", TRIGGER_PREFIXES)

telegram_book_listener = TelegramBookBotListener()
