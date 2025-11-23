from loguru import logger
import sys
import os
import asyncio
from typing import Any
import re
import html
from datetime import datetime, timezone
from dotenv import load_dotenv
from pyrogram import Client, enums
from pyrogram.raw import functions as raw_functions
from pyrogram.raw import types as raw_types
from pyrogram.errors import RPCError, MessageNotModified

logger.remove()
logger.add(
    sys.stdout,
    format="| <magenta>{time:YYYY-MM-DD HH:mm:ss}</magenta> | <cyan><level>{level: <8}</level></cyan> | {message}",
    level="INFO",
    colorize=True,
)
logger.add(
    "userbot.log",
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
    channel_id = os.getenv("CHANNEL_ID")

    if not api_id or not api_hash:
        logger.error("Missing API_ID or API_HASH in environment")
        return

    try:
        api_id = int(api_id)
    except ValueError:
        logger.error("API_ID must be an integer")
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
        try:
            gifts = await app.invoke(raw_functions.payments.GetStarGifts(hash=0))
            auction_gift = None
            while auction_gift is None:
                for g in getattr(gifts, "gifts", []):
                    if getattr(g, "auction", False) and not getattr(g, "sold_out", False):
                        auction_gift = g
                        break
                if auction_gift is None:
                    logger.info("No auctions found; retry in 30s")
                    await asyncio.sleep(30)
                    gifts = await app.invoke(raw_functions.payments.GetStarGifts(hash=0))

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

            def html_visible_len(s: str) -> int:
                return len(re.sub(r"<[^>]*>", "", s))

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

            def fmt_end_date(ts: int) -> str:
                try:
                    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                except Exception:
                    return ""
                return dt.strftime("%d.%m.%y %H:%M")

            def build_text(state: dict[str, Any]) -> str:
                if not isinstance(state, dict):
                    state = {}
                EMO_HAMMER = '<emoji id="5411180428092533606">🔨</emoji>'
                EMO_CLOCK = '<emoji id="5409044257388390754">🕓</emoji>'
                EMO_GIFT_TOTAL = '<emoji id="5424766281528147222">🎁</emoji>'
                EMO_GIFT_LEFT = '<emoji id="5411480216809792207">🎁</emoji>'
                EMO_UP = '<emoji id="5409128576186347318">⬆️</emoji>'
                EMO_CROWN = '<emoji id="5411258570727517292">👑</emoji>'
                EMO_STAR = '<emoji id="5472092560522511055">⭐️</emoji>'
                
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
                parts: list[str] = []
                parts.append(f"{EMO_HAMMER} {header}")
                parts.append("")
                parts.append(f"{EMO_CLOCK} <b>Next Round In:</b> {next_in}")
                parts.append(f"{EMO_GIFT_TOTAL} <b>Total Rounds:</b> {current_round}/{total_rounds}")
                parts.append("")
                parts.append(f"{EMO_GIFT_LEFT} <b>Gifts Left:</b> {gifts_left}/{availability_total}")
                parts.append(f"{EMO_UP} <b>Min Bid:</b> {min_bid_amount} {EMO_STAR} ≈ {fmt_usd(min_bid_amount)}")
                parts.append("")
                parts.append(f"{EMO_CROWN} <b>Top</b> {int(gifts_per_round or len(bids_sorted) or 0)} Bids:")
                inner_lines: list[str] = []
                for b in bids_sorted:
                    amount = b.get("amount")
                    pos = b.get("pos")
                    usd = fmt_usd(amount or 0)
                    inner_lines.append(f"{pos}. {amount} {EMO_STAR} ≈ {usd}")
                inner = "\n".join(inner_lines)
                parts.append(f"<blockquote expandable>{inner}</blockquote>")
                parts.append("<b>Made By @Th3ryks</b>")
                updated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                parts.append(f"{EMO_CLOCK} <b>Last Update:</b> {updated}")
                return "\n".join(parts)

            async def handle_other(agift: Any) -> None:
                if getattr(agift, "auction_slug", None):
                    auct = raw_types.InputStarGiftAuctionSlug(slug=agift.auction_slug)
                    a_slug = agift.auction_slug
                else:
                    auct = raw_types.InputStarGiftAuction(gift_id=agift.id)
                    a_slug = str(agift.id)

                async def gs() -> Any:
                    res = await app.invoke(
                        raw_functions.payments.GetStarGiftAuctionState(
                            auction=auct,
                            version=0,
                        )
                    )
                    data = _to_serializable(res)
                    data["gift"] = _to_serializable(agift)
                    return data

                def build(state: dict[str, Any]) -> str:
                    if not isinstance(state, dict):
                        state = {}
                    EMO_H = '<emoji id="5411180428092533606">🔨</emoji>'
                    EMO_C = '<emoji id="5409044257388390754">🕓</emoji>'
                    EMO_GT = '<emoji id="5424766281528147222">🎁</emoji>'
                    EMO_GL = '<emoji id="5411480216809792207">🎁</emoji>'
                    EMO_UP = '<emoji id="5409128576186347318">⬆️</emoji>'
                    EMO_CR = '<emoji id="5411258570727517292">👑</emoji>'
                    EMO_ST = '<emoji id="5472092560522511055">⭐️</emoji>'
                    gift = state.get("gift", {})
                    s = state.get("state", {})
                    title = gift.get("title") or "Auction"
                    availability_total = gift.get("availability_total") or 0
                    gpr = gift.get("gifts_per_round") or 0
                    next_ts = s.get("next_round_at") or state.get("next_round_at") or 0
                    current_round = state.get("current_round") or s.get("current_round") or 0
                    total_rounds = state.get("total_rounds") or s.get("total_rounds") or 0
                    gifts_left = state.get("gifts_left") or gift.get("availability_remains") or 0
                    min_bid_amount = s.get("min_bid_amount") or state.get("min_bid_amount") or 0
                    bid_levels = s.get("bid_levels") or state.get("bid_levels") or []
                    bids_sorted = sorted([b for b in bid_levels if isinstance(b, dict)], key=lambda x: x.get("pos", 0))[: max(1, int(gpr) or (len(bid_levels) if isinstance(bid_levels, list) else 4)) ]
                    slug_clean = str(a_slug or "").replace("`", "").strip()
                    header = f"<a href=\"https://t.me/auction/{html_escape(slug_clean)}\"><b>{html_escape(title)}</b></a>"
                    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
                    remain_sec = (int(next_ts) - now_ts) if next_ts else 0
                    next_in = fmt_delta(remain_sec)
                    parts = [
                        f"{EMO_H} {header}",
                        "",
                        f"{EMO_C} <b>Next Round In:</b> {next_in}",
                        f"{EMO_GT} <b>Total Rounds:</b> {current_round}/{total_rounds}",
                        "",
                        f"{EMO_GL} <b>Gifts Left:</b> {gifts_left}/{availability_total}",
                        f"{EMO_UP} <b>Min Bid:</b> {min_bid_amount} {EMO_ST} ≈ {fmt_usd(min_bid_amount)}",
                        "",
                        f"{EMO_CR} <b>Top</b> {int(gpr or len(bids_sorted) or 0)} Bids:",
                    ]
                    inner_lines: list[str] = []
                    for b in bids_sorted:
                        amount = b.get("amount")
                        pos = b.get("pos")
                        usd = fmt_usd(amount or 0)
                        inner_lines.append(f"{pos}. {amount} {EMO_ST} ≈ {usd}")
                    inner_block = "\n".join(inner_lines)
                    parts.append(f"<blockquote expandable>{inner_block}</blockquote>")
                    parts.append("<b>Made By @Th3ryks</b>")
                    updated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    parts.append(f"{EMO_C} <b>Last Update:</b> {updated}")
                    return "\n".join(parts)

                target_chat_local = resolve_target_chat(channel_id, "@AuctionStateTG")
                s0 = await gs()
                t0 = build(s0)
                try:
                    m0 = await app.send_message(chat_id=target_chat_local, text=t0, parse_mode=enums.ParseMode.HTML)
                except RPCError as e:
                    emsg = str(e).lower()
                    if "peer" in emsg or "chat not found" in emsg or "peer_id_invalid" in emsg:
                        m0 = await app.send_message(chat_id="@AuctionStateTG", text=t0, parse_mode=enums.ParseMode.HTML)
                    else:
                        raise

                async def lp() -> None:
                    last_round_l = s0.get("current_round") or s0.get("state", {}).get("current_round") or 0
                    last_msg_id_l = m0.id
                    last_text_l = t0
                    finished_sent_l = False
                    while True:
                        try:
                            sn = await gs()
                            now_ts_l = int(datetime.now(tz=timezone.utc).timestamp())
                            next_ts_l = sn.get("state", {}).get("next_round_at") or sn.get("next_round_at") or 0
                            end_ts_l = sn.get("state", {}).get("end_date") or sn.get("end_date") or 0
                            remain_next_l = max(0, int(next_ts_l) - now_ts_l) if next_ts_l else 60
                            remain_end_l = max(0, int(end_ts_l) - now_ts_l) if end_ts_l else 0
                            period_l = 30 if remain_next_l <= 60 else 60
                            new_round_l = sn.get("current_round") or sn.get("state", {}).get("current_round") or 0
                            if remain_next_l > 0 and remain_next_l <= 10:
                                await asyncio.sleep(remain_next_l)
                                sn = await gs()
                                now_ts_l = int(datetime.now(tz=timezone.utc).timestamp())
                                next_ts_l = sn.get("state", {}).get("next_round_at") or sn.get("next_round_at") or 0
                                end_ts_l = sn.get("state", {}).get("end_date") or sn.get("end_date") or 0
                                remain_next_l = max(0, int(next_ts_l) - now_ts_l) if next_ts_l else 0
                                remain_end_l = max(0, int(end_ts_l) - now_ts_l) if end_ts_l else 0
                                new_round_l = sn.get("current_round") or sn.get("state", {}).get("current_round") or 0
                            if end_ts_l and remain_end_l <= 0 and not finished_sent_l:
                                EMO_C = '<emoji id="5409044257388390754">🕓</emoji>'
                                def fmt_dt_l(ts: int) -> str:
                                    try:
                                        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                                        return dt.strftime("%b %d, %Y, %H:%M UTC")
                                    except Exception:
                                        return ""
                                def fmt_dur_l(seconds: int) -> str:
                                    seconds = max(0, int(seconds))
                                    d = seconds // 86400
                                    h = (seconds % 86400) // 3600
                                    m = (seconds % 3600) // 60
                                    parts = []
                                    if d:
                                        parts.append(f"{d} day" + ("s" if d != 1 else ""))
                                    if h:
                                        parts.append(f"{h} hour" + ("s" if h != 1 else ""))
                                    parts.append(f"{m} minute" + ("s" if m != 1 else ""))
                                    if len(parts) > 1:
                                        return ", ".join(parts[:-1]) + " and " + parts[-1]
                                    return parts[0]
                                def fmt_stars_l(n: float) -> str:
                                    try:
                                        iv = int(round(float(n)))
                                    except Exception:
                                        iv = 0
                                    s = f"{iv:,}".replace(",", " ")
                                    return s
                                s2_l = sn.get("state", {})
                                EMO_STAR_L = "\u2B50\uFE0F"
                                gift2_l = sn.get("gift", {})
                                title2_l = html_escape(gift2_l.get("title") or "Auction")
                                start_ts2_l = s2_l.get("start_date") or sn.get("start_date") or 0
                                end_ts2_l = s2_l.get("end_date") or sn.get("end_date") or 0
                                bids2_l = s2_l.get("bid_levels") or sn.get("bid_levels") or []
                                amounts2_l = [float(b.get("amount", 0.0)) for b in bids2_l if isinstance(b, dict)]
                                avg2_l = sum(amounts2_l) / len(amounts2_l) if amounts2_l else 0.0
                                lasted2_l = fmt_dur_l((int(end_ts2_l) - int(start_ts2_l)) if (start_ts2_l and end_ts2_l) else 0)
                                finished_text_l = "\n".join([
                                    f"<emoji id=\"5411180428092533606\">🔨</emoji> <a href=\"https://t.me/auction/{html_escape(str(a_slug))}\"><b>{title2_l}</b></a> auction has <b>finished</b>!",
                                    f"<b>Auction started:</b> {fmt_dt_l(start_ts2_l)}" if start_ts2_l else "",
                                    f"<b>Auction ended:</b> {fmt_dt_l(end_ts2_l)}" if end_ts2_l else "",
                                    "",
                                    f"<b>Average gift price:</b> {fmt_stars_l(avg2_l)} {EMO_STAR_L}",
                                    f"<b>Auction lasted:</b> {lasted2_l}",
                                    "",
                                    "Done By @Th3ryks",
                                    f"{EMO_C} <b>Last Update:</b> {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                                ])
                                try:
                                    nm_l = await app.send_message(chat_id=target_chat_local, text=finished_text_l, parse_mode=enums.ParseMode.HTML)
                                except RPCError as e:
                                    emsg = str(e).lower()
                                    if "peer" in emsg or "chat not found" in emsg or "peer_id_invalid" in emsg:
                                        nm_l = await app.send_message(chat_id="@AuctionStateTG", text=finished_text_l, parse_mode=enums.ParseMode.HTML)
                                    else:
                                        raise
                                last_msg_id_l = nm_l.id
                                finished_sent_l = True
                                last_text_l = finished_text_l
                            if remain_next_l <= 0:
                                ended_lines_l = last_text_l.split("\n")
                                if len(ended_lines_l) > 2:
                                    ended_lines_l[2] = "<emoji id=\"5409044257388390754\">🕓</emoji> Round Ended"
                                ended_text_l = "\n".join(ended_lines_l)
                                try:
                                    await app.edit_message_text(chat_id=target_chat_local, message_id=last_msg_id_l, text=ended_text_l, parse_mode=enums.ParseMode.HTML)
                                except MessageNotModified:
                                    pass
                                except RPCError as e:
                                    logger.error(f"Edit failed: {e}")
                                new_state_l = sn
                                if new_round_l == last_round_l:
                                    for _ in range(5):
                                        await asyncio.sleep(1)
                                        new_state_l = await gs()
                                        nr_check_l = new_state_l.get("current_round") or new_state_l.get("state", {}).get("current_round") or 0
                                        if nr_check_l != last_round_l:
                                            new_round_l = nr_check_l
                                            break
                                text_new_l = build(new_state_l)
                                try:
                                    nm_l2 = await app.send_message(chat_id=target_chat_local, text=text_new_l, parse_mode=enums.ParseMode.HTML)
                                except RPCError as e:
                                    emsg = str(e).lower()
                                    if "peer" in emsg or "chat not found" in emsg or "peer_id_invalid" in emsg:
                                        nm_l2 = await app.send_message(chat_id="@AuctionStateTG", text=text_new_l, parse_mode=enums.ParseMode.HTML)
                                    else:
                                        raise
                                last_msg_id_l = nm_l2.id
                                last_round_l = new_round_l or last_round_l
                                last_text_l = text_new_l
                            elif new_round_l != last_round_l:
                                ended_lines_l = last_text_l.split("\n")
                                if len(ended_lines_l) > 2:
                                    ended_lines_l[2] = "<emoji id=\"5409044257388390754\">🕓</emoji> Round Ended"
                                ended_text_l = "\n".join(ended_lines_l)
                                try:
                                    await app.edit_message_text(chat_id=target_chat_local, message_id=last_msg_id_l, text=ended_text_l, parse_mode=enums.ParseMode.HTML)
                                except MessageNotModified:
                                    pass
                                except RPCError as e:
                                    logger.error(f"Edit failed: {e}")
                                text_new_l = build(sn)
                                try:
                                    nm_l3 = await app.send_message(chat_id=target_chat_local, text=text_new_l, parse_mode=enums.ParseMode.HTML)
                                except RPCError as e:
                                    emsg = str(e).lower()
                                    if "peer" in emsg or "chat not found" in emsg or "peer_id_invalid" in emsg:
                                        nm_l3 = await app.send_message(chat_id="@AuctionStateTG", text=text_new_l, parse_mode=enums.ParseMode.HTML)
                                    else:
                                        raise
                                last_msg_id_l = nm_l3.id
                                last_round_l = new_round_l or last_round_l
                                last_text_l = text_new_l
                            else:
                                text_new_l = build(sn)
                                if text_new_l != last_text_l:
                                    try:
                                        await app.edit_message_text(chat_id=target_chat_local, message_id=last_msg_id_l, text=text_new_l, parse_mode=enums.ParseMode.HTML)
                                    except MessageNotModified:
                                        pass
                                    except RPCError as e:
                                        emsg = str(e)
                                        if "FLOOD_WAIT" in emsg:
                                            import re as _re
                                            m_l = _re.search(r"FLOOD_WAIT_?(\d+)", emsg)
                                            wait_l = int(m_l.group(1)) if m_l else 60
                                            logger.error(f"Flood wait: sleeping {wait_l}s")
                                            await asyncio.sleep(wait_l + 1)
                                        else:
                                            logger.error(f"Edit failed: {e}")
                                    last_text_l = text_new_l
                            await asyncio.sleep(period_l)
                        except Exception as e:
                            logger.error(f"Update loop error: {e}")
                            await asyncio.sleep(10)
                await lp()

            other_auctions = [g for g in getattr(gifts, "gifts", []) if getattr(g, "auction", False) and not getattr(g, "sold_out", False) and g is not auction_gift]
            for og in other_auctions:
                asyncio.create_task(handle_other(og))

            active_keys: set[str] = set()
            for g in getattr(gifts, "gifts", []):
                if getattr(g, "auction", False) and not getattr(g, "sold_out", False):
                    k = g.auction_slug if getattr(g, "auction_slug", None) else str(g.id)
                    active_keys.add(k)

            async def discover() -> None:
                while True:
                    gd = await app.invoke(raw_functions.payments.GetStarGifts(hash=0))
                    aucs = [x for x in getattr(gd, "gifts", []) if getattr(x, "auction", False) and not getattr(x, "sold_out", False)]
                    for ag in aucs:
                        k = ag.auction_slug if getattr(ag, "auction_slug", None) else str(ag.id)
                        if k not in active_keys:
                            asyncio.create_task(handle_other(ag))
                            active_keys.add(k)
                    await asyncio.sleep(30)
            asyncio.create_task(discover())

            state = await get_state()
            text = build_text(state)
            target_chat = resolve_target_chat(channel_id, "@AuctionStateTG")
            try:
                msg = await app.send_message(chat_id=target_chat, text=text, parse_mode=enums.ParseMode.HTML)
            except RPCError as e:
                emsg = str(e).lower()
                if "peer" in emsg or "chat not found" in emsg or "peer_id_invalid" in emsg:
                    msg = await app.send_message(chat_id="@AuctionStateTG", text=text, parse_mode=enums.ParseMode.HTML)
                else:
                    raise
            logger.info("Initial auction message sent")

            async def loop() -> None:
                last_round = state.get("current_round") or state.get("state", {}).get("current_round") or 0
                last_msg_id = msg.id
                last_text = text
                finished_sent = False
                while True:
                    try:
                        state_new = await get_state()
                        now_ts = int(datetime.now(tz=timezone.utc).timestamp())
                        next_ts_new = state_new.get("state", {}).get("next_round_at") or state_new.get("next_round_at") or 0
                        end_ts_new = state_new.get("state", {}).get("end_date") or state_new.get("end_date") or 0
                        remain_next = max(0, int(next_ts_new) - now_ts) if next_ts_new else 60
                        remain_end = max(0, int(end_ts_new) - now_ts) if end_ts_new else 0
                        period = 30 if remain_next <= 60 else 60

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
                            EMO_CLOCK = '<emoji id="5409044257388390754">🕓</emoji>'
                            def fmt_dt(ts: int) -> str:
                                try:
                                    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                                    return dt.strftime("%b %d, %Y, %H:%M UTC")
                                except Exception:
                                    return ""

                            def fmt_duration(seconds: int) -> str:
                                seconds = max(0, int(seconds))
                                d = seconds // 86400
                                h = (seconds % 86400) // 3600
                                m = (seconds % 3600) // 60
                                parts = []
                                if d:
                                    parts.append(f"{d} day" + ("s" if d != 1 else ""))
                                if h:
                                    parts.append(f"{h} hour" + ("s" if h != 1 else ""))
                                parts.append(f"{m} minute" + ("s" if m != 1 else ""))
                                if len(parts) > 1:
                                    return ", ".join(parts[:-1]) + " and " + parts[-1]
                                return parts[0]

                            def fmt_stars(n: float) -> str:
                                try:
                                    iv = int(round(float(n)))
                                except Exception:
                                    iv = 0
                                s = f"{iv:,}".replace(",", " ")
                                return s

                            s2 = state_new.get("state", {})
                            EMO_STAR = "\u2B50\uFE0F"
                            gift2 = state_new.get("gift", {})
                            title2 = html_escape(gift2.get("title") or "Auction")
                            start_ts2 = s2.get("start_date") or state_new.get("start_date") or 0
                            end_ts2 = s2.get("end_date") or state_new.get("end_date") or 0
                            bids2 = s2.get("bid_levels") or state_new.get("bid_levels") or []
                            amounts2 = [float(b.get("amount", 0.0)) for b in bids2 if isinstance(b, dict)]
                            avg2 = sum(amounts2) / len(amounts2) if amounts2 else 0.0
                            lasted2 = fmt_duration((int(end_ts2) - int(start_ts2)) if (start_ts2 and end_ts2) else 0)

                            finished_text = "\n".join([
                                f"<emoji id=\"5411180428092533606\">🔨</emoji> <a href=\"https://t.me/auction/{html_escape(str(auction_slug))}\"><b>{title2}</b></a> auction has <b>finished</b>!",
                                f"<b>Auction started:</b> {fmt_dt(start_ts2)}" if start_ts2 else "",
                                f"<b>Auction ended:</b> {fmt_dt(end_ts2)}" if end_ts2 else "",
                                "",
                                f"<b>Average gift price:</b> {fmt_stars(avg2)} {EMO_STAR}",
                                f"<b>Auction lasted:</b> {lasted2}",
                                "",
                                "Done By @Th3ryks",
                                f"{EMO_CLOCK} <b>Last Update:</b> {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                            ])
                            try:
                                new_msg = await app.send_message(chat_id=target_chat, text=finished_text, parse_mode=enums.ParseMode.HTML)
                            except RPCError as e:
                                emsg = str(e).lower()
                                if "peer" in emsg or "chat not found" in emsg or "peer_id_invalid" in emsg:
                                    new_msg = await app.send_message(chat_id="@AuctionStateTG", text=finished_text, parse_mode=enums.ParseMode.HTML)
                                else:
                                    raise
                            last_msg_id = new_msg.id
                            finished_sent = True
                            last_text = finished_text
                        if remain_next <= 0:
                            ended_lines = last_text.split("\n")
                            if len(ended_lines) > 2:
                                ended_lines[2] = "<emoji id=\"5409044257388390754\">🕓</emoji> Round Ended"
                            ended_text = "\n".join(ended_lines)
                            try:
                                await app.edit_message_text(chat_id=target_chat, message_id=last_msg_id, text=ended_text, parse_mode=enums.ParseMode.HTML)
                            except MessageNotModified:
                                pass
                            except RPCError as e:
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
                                new_msg = await app.send_message(chat_id=target_chat, text=text_new, parse_mode=enums.ParseMode.HTML)
                            except RPCError as e:
                                emsg = str(e).lower()
                                if "peer" in emsg or "chat not found" in emsg or "peer_id_invalid" in emsg:
                                    new_msg = await app.send_message(chat_id="@AuctionStateTG", text=text_new, parse_mode=enums.ParseMode.HTML)
                                else:
                                    raise
                            last_msg_id = new_msg.id
                            last_round = new_round or last_round
                            last_text = text_new
                        elif new_round != last_round:
                            ended_lines = last_text.split("\n")
                            if len(ended_lines) > 2:
                                ended_lines[2] = "<emoji id=\"5409044257388390754\">🕓</emoji> Round Ended"
                            ended_text = "\n".join(ended_lines)
                            try:
                                await app.edit_message_text(chat_id=target_chat, message_id=last_msg_id, text=ended_text, parse_mode=enums.ParseMode.HTML)
                            except MessageNotModified:
                                pass
                            except RPCError as e:
                                logger.error(f"Edit failed: {e}")
                            text_new = build_text(state_new)
                            try:
                                new_msg = await app.send_message(chat_id=target_chat, text=text_new, parse_mode=enums.ParseMode.HTML)
                            except RPCError as e:
                                emsg = str(e).lower()
                                if "peer" in emsg or "chat not found" in emsg or "peer_id_invalid" in emsg:
                                    new_msg = await app.send_message(chat_id="@AuctionStateTG", text=text_new, parse_mode=enums.ParseMode.HTML)
                                else:
                                    raise
                            last_msg_id = new_msg.id
                            last_round = new_round or last_round
                            last_text = text_new
                        else:
                            text_new = build_text(state_new)
                            if text_new != last_text:
                                try:
                                    await app.edit_message_text(chat_id=target_chat, message_id=last_msg_id, text=text_new, parse_mode=enums.ParseMode.HTML)
                                except MessageNotModified:
                                    pass
                                except RPCError as e:
                                    emsg = str(e)
                                    if "FLOOD_WAIT" in emsg:
                                        import re as _re
                                        m = _re.search(r"FLOOD_WAIT_?(\d+)", emsg)
                                        wait = int(m.group(1)) if m else 60
                                        logger.error(f"Flood wait: sleeping {wait}s")
                                        await asyncio.sleep(wait + 1)
                                    else:
                                        logger.error(f"Edit failed: {e}")
                                last_text = text_new

                        await asyncio.sleep(period)
                    except Exception as e:
                        logger.error(f"Update loop error: {e}")
                        await asyncio.sleep(10)

            await loop()
        finally:
            pass

async def main() -> None:
    await fetch_auction_state()


if __name__ == "__main__":
    asyncio.run(main())
