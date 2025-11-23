from loguru import logger
import sys
import os
import asyncio
from typing import Any
from datetime import datetime, timezone
from dotenv import load_dotenv
import html
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from pyrogram import Client
from pyrogram.raw import functions as raw_functions
from pyrogram.raw import types as raw_types

logger.remove()
logger.add(
    sys.stdout,
    format="| <magenta>{time:YYYY-MM-DD HH:mm:ss}</magenta> | <cyan><level>{level: <8}</level></cyan> | {message}",
    level="INFO",
    colorize=True,
)
logger.add(
    "bot.log",
    format="| <magenta>{time:YYYY-MM-DD HH:mm:ss}</magenta> | <cyan><level>{level: <8}</level></cyan> | {message}",
    level="INFO",
    colorize=False,
)

def _to_serializable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return bytes(obj).hex()
    if isinstance(obj, (list, tuple, set)):
        return [ _to_serializable(x) for x in obj ]
    if isinstance(obj, dict):
        return { str(k): _to_serializable(v) for k, v in obj.items() }
    slots = getattr(obj, "__slots__", None)
    if slots:
        data: dict[str, Any] = {}
        for k in slots:
            if not isinstance(k, str) or k.startswith("_"):
                continue
            try:
                v = getattr(obj, k)
            except Exception:
                continue
            data[k] = _to_serializable(v)
        data["__class__"] = obj.__class__.__name__
        data["__module__"] = obj.__class__.__module__
        return data
    if hasattr(obj, "__dict__"):
        data = {}
        for k, v in obj.__dict__.items():
            if k.startswith("_"):
                continue
            data[k] = _to_serializable(v)
        data["__class__"] = obj.__class__.__name__
        data["__module__"] = obj.__class__.__module__
        return data
    return str(obj)

def resolve_target_chat(channel_id: str | None, username_fallback: str | None = None) -> int | str | None:
    if not channel_id:
        return username_fallback
    s = str(channel_id).strip()
    if s.startswith("@"):
        return s
    try:
        if s.startswith("-100"):
            return int(s)
        n = int(s)
        if n > 0:
            return int(f"-100{s}")
        return n
    except Exception:
        return username_fallback or s

async def fetch_auction_state() -> None:
    load_dotenv()
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    bot_token = os.getenv("BOT_TOKEN")
    channel_id = os.getenv("CHANNEL_ID")

    if not api_id or not api_hash:
        logger.error("Missing API_ID or API_HASH in environment")
        return

    try:
        api_id = int(api_id)
    except ValueError:
        logger.error("API_ID must be an integer")
        return

    if not bot_token:
        logger.error("Missing BOT_TOKEN in environment")
        return

    app = Client(
        "account",
        api_id=api_id,
        api_hash=api_hash,
        workdir=os.getcwd(),
        in_memory=False,
        no_updates=True,
    )

    async with app:
        bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            gifts = await app.invoke(raw_functions.payments.GetStarGifts(hash=0))
            auction_gift = None
            for g in getattr(gifts, "gifts", []):
                if getattr(g, "auction", False) and not getattr(g, "sold_out", False):
                    auction_gift = g
                    break
            if auction_gift is None:
                logger.error("No auction-enabled star gifts available")
                return

            if getattr(auction_gift, "auction_slug", None):
                auction = raw_types.InputStarGiftAuctionSlug(slug=auction_gift.auction_slug)
                auction_slug = auction_gift.auction_slug
            else:
                auction = raw_types.InputStarGiftAuction(gift_id=auction_gift.id)
                auction_slug = str(auction_gift.id)

            async def get_state() -> Any:
                res = await app.invoke(
                    raw_functions.payments.GetStarGiftAuctionState(
                        auction=auction,
                        version=0,
                    )
                )
                data = _to_serializable(res)
                return data
            def html_escape(text: str) -> str:
                return html.escape(str(text))

            def fmt_ts(ts: int) -> str:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M:%S UTC")

            def fmt_usd(stars: int | float) -> str:
                usd = float(stars) * 0.015
                s = f"{usd:.2f}".rstrip("0").rstrip(".")
                return f"${s}"

            def fmt_delta(seconds: int) -> str:
                seconds = max(0, int(seconds))
                h = seconds // 3600
                m = (seconds % 3600) // 60
                s = seconds % 60
                parts: list[str] = []
                if h:
                    parts.append(f"{h}h")
                if m or h:
                    parts.append(f"{m}m")
                parts.append(f"{s}s")
                return " ".join(parts)

            

            def build_text(state: dict[str, Any]) -> str:
                if not isinstance(state, dict):
                    state = {}
                EMO_HAMMER = chr(0x1F528)
                EMO_CLOCK = chr(0x1F553)
                EMO_GIFT = chr(0x1F381)
                EMO_UP = "\u2B06\uFE0F"
                EMO_CROWN = chr(0x1F451)
                EMO_STAR = "\u2B50\uFE0F"
                EMO_NUM = chr(0x1F522)
                gift = state.get("gift", {})
                s = state.get("state", {})
                title = gift.get("title") or "Auction"
                availability_total = gift.get("availability_total") or 0
                gifts_per_round = gift.get("gifts_per_round") or 0

                next_ts = s.get("next_round_at") or state.get("next_round_at") or 0
                current_round = state.get("current_round") or s.get("current_round") or 0
                total_rounds = state.get("total_rounds") or s.get("total_rounds") or 0
                gifts_left = state.get("gifts_left") or gift.get("availability_remains") or 0
                min_bid_amount = s.get("min_bid_amount") or state.get("min_bid_amount") or 0
                

                bid_levels = s.get("bid_levels") or state.get("bid_levels") or []
                bids_sorted = sorted(
                    [b for b in bid_levels if isinstance(b, dict)],
                    key=lambda x: x.get("pos", 0)
                )[: max(1, int(gifts_per_round) or (len(bid_levels) if isinstance(bid_levels, list) else 4)) ]

                slug_clean = str(auction_slug or "").replace("`", "").strip()
                header = f"<a href=\"https://t.me/auction/{html_escape(slug_clean)}\"><b>{html_escape(title)}</b></a>"
                now_ts = int(datetime.now(tz=timezone.utc).timestamp())
                remain_sec = (int(next_ts) - now_ts) if next_ts else 0
                next_in = fmt_delta(remain_sec)

                lines = [
                    f"{EMO_HAMMER} {header}",
                    "",
                    f"{EMO_CLOCK} <b>Next Round In:</b> {next_in}",
                    f"{EMO_NUM} <b>Total Rounds:</b> {current_round}/{total_rounds}",
                    "",
                    f"{EMO_GIFT} <b>Gifts Left:</b> {gifts_left}/{availability_total}",
                    f"{EMO_UP} <b>Min Bid:</b> {min_bid_amount} {EMO_STAR} ≈ {fmt_usd(min_bid_amount)}",
                    "",
                    f"{EMO_CROWN} <b>Top {int(gifts_per_round or len(bids_sorted) or 0)} Bids:</b>",
                ]

                updated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

                inner_lines: list[str] = []
                for b in bids_sorted:
                    amount = b.get("amount")
                    pos = b.get("pos")
                    usd = fmt_usd(amount or 0)
                    inner_lines.append(f"{pos}. {amount} {EMO_STAR} ≈ {usd}")
                inner = "\n".join(inner_lines)

                lines.append(f"<blockquote expandable>{inner}</blockquote>")

                lines.append("")
                lines.append("<b>Made By @Th3ryks</b>")
                lines.append(f"{EMO_CLOCK} <b>Last Update:</b> {updated}")
                return "\n".join(lines)

            state = await get_state()
            text = build_text(state)
            target_chat = resolve_target_chat(channel_id, "@AuctionStateTG")
            try:
                msg = await bot.send_message(chat_id=target_chat, text=text)
            except TelegramBadRequest as e:
                emsg = str(e).lower()
                if "chat not found" in emsg:
                    msg = await bot.send_message(chat_id="@AuctionStateTG", text=text)
                else:
                    raise
            logger.info("Initial auction message sent")

            async def loop() -> None:
                last_round = state.get("current_round") or state.get("state", {}).get("current_round") or 0
                last_msg_id = msg.message_id
                last_text = text
                finished_sent = False
                while True:
                    try:
                        state_new = await get_state()
                        now_ts = int(datetime.now(tz=timezone.utc).timestamp())
                        next_ts_new = state_new.get("state", {}).get("next_round_at") or state_new.get("next_round_at") or 0
                        end_ts_new = state_new.get("state", {}).get("end_date") or state_new.get("end_date") or 0
                        remain_next = max(0, int(next_ts_new) - now_ts) if next_ts_new else 30
                        remain_end = max(0, int(end_ts_new) - now_ts) if end_ts_new else 0
                        period = 10 if remain_next <= 70 else 30

                        new_round = state_new.get("current_round") or state_new.get("state", {}).get("current_round") or 0
                        if remain_next > 0 and remain_next <= 10:
                            await asyncio.sleep(remain_next)
                            state_new = await get_state()
                            now_ts = int(datetime.now(tz=timezone.utc).timestamp())
                            next_ts_new = state_new.get("state", {}).get("next_round_at") or state_new.get("next_round_at") or 0
                            end_ts_new = state_new.get("state", {}).get("end_date") or state_new.get("end_date") or 0
                            remain_next = max(0, int(next_ts_new) - now_ts) if next_ts_new else 0
                            remain_end = max(0, int(end_ts_new) - now_ts) if end_ts_new else 0
                            new_round = state_new.get("current_round") or state_new.get("state", {}).get("current_round") or 0
                        if end_ts_new and remain_end <= 0 and not finished_sent:
                            finished_lines = [
                                f"{chr(0x1F528)} <a href=\"https://t.me/auction/{html_escape(str(auction_slug))}\">{html_escape(state_new.get('gift', {}).get('title') or 'Auction')}</a>",
                                "",
                                "🕓 Auction Finished",
                                "Done By @Th3ryks",
                                f"🕓 Last Update: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                            ]
                            finished_text = "\n".join(finished_lines)
                            try:
                                new_msg = await bot.send_message(chat_id=target_chat, text=finished_text)
                            except TelegramBadRequest as e:
                                emsg = str(e).lower()
                                if "chat not found" in emsg:
                                    new_msg = await bot.send_message(chat_id="@AuctionStateTG", text=finished_text)
                                else:
                                    raise
                            last_msg_id = new_msg.message_id
                            finished_sent = True
                            last_text = finished_text
                        elif remain_next <= 0:
                            ended_lines = last_text.split("\n")
                            if len(ended_lines) > 2:
                                ended_lines[2] = "🕓 Round Ended"
                            ended_text = "\n".join(ended_lines)
                            try:
                                await bot.edit_message_text(chat_id=target_chat, message_id=last_msg_id, text=ended_text)
                            except TelegramBadRequest as e:
                                logger.error(f"Edit failed: {e}")
                            new_state = state_new
                            if new_round == last_round:
                                for _ in range(5):
                                    await asyncio.sleep(1)
                                    new_state = await get_state()
                                    nr_check = new_state.get("current_round") or new_state.get("state", {}).get("current_round") or 0
                                    if nr_check != last_round:
                                        new_round = nr_check
                                        break
                            text_new = build_text(new_state)
                            try:
                                new_msg = await bot.send_message(chat_id=target_chat, text=text_new)
                            except TelegramBadRequest as e:
                                emsg = str(e).lower()
                                if "chat not found" in emsg:
                                    new_msg = await bot.send_message(chat_id="@AuctionStateTG", text=text_new)
                                else:
                                    raise
                            last_msg_id = new_msg.message_id
                            last_round = new_round or last_round
                            last_text = text_new
                        elif new_round != last_round:
                            ended_lines = last_text.split("\n")
                            if len(ended_lines) > 2:
                                ended_lines[2] = "🕓 Round Ended"
                            ended_text = "\n".join(ended_lines)
                            try:
                                await bot.edit_message_text(chat_id=target_chat, message_id=last_msg_id, text=ended_text)
                            except TelegramBadRequest as e:
                                logger.error(f"Edit failed: {e}")
                            text_new = build_text(state_new)
                            try:
                                new_msg = await bot.send_message(chat_id=target_chat, text=text_new)
                            except TelegramBadRequest as e:
                                emsg = str(e).lower()
                                if "chat not found" in emsg:
                                    new_msg = await bot.send_message(chat_id="@AuctionStateTG", text=text_new)
                                else:
                                    raise
                            last_msg_id = new_msg.message_id
                            last_round = new_round or last_round
                            last_text = text_new
                        else:
                            text_new = build_text(state_new)
                            if text_new != last_text:
                                try:
                                    await bot.edit_message_text(chat_id=target_chat, message_id=last_msg_id, text=text_new)
                                except TelegramBadRequest as e:
                                    logger.error(f"Edit failed: {e}")
                                last_text = text_new

                        await asyncio.sleep(period)
                    except Exception as e:
                        logger.error(f"Update loop error: {e}")
                        await asyncio.sleep(10)

            await loop()
        finally:
            await bot.session.close()

async def main() -> None:
    await fetch_auction_state()


if __name__ == "__main__":
    asyncio.run(main())