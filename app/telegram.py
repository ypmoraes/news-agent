"""Telegram Bot API client: receive commands and send/broadcast messages."""
import html
import logging
import time
from datetime import datetime

import requests

import config

log = logging.getLogger("telegram")
BASE = "https://api.telegram.org/bot{t}/{m}"


def _url(method):
    return BASE.format(t=config.BOT_TOKEN, m=method)


def get_updates(offset, timeout):
    """Long-poll for incoming updates. Returns a list (possibly empty)."""
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(_url("getUpdates"), params=params, timeout=timeout + 15)
        r.raise_for_status()
        return r.json().get("result", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("getUpdates failed: %s", exc)
        time.sleep(3)  # back off so a persistent error doesn't spin the loop
        return []


def send_message(chat_id, text):
    """Send one message. Returns (ok, status_code)."""
    try:
        r = requests.post(
            _url("sendMessage"),
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if r.status_code == 403:  # user blocked or removed the bot
            return False, 403
        r.raise_for_status()
        return True, r.status_code
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        log.warning("send to %s failed: %s", chat_id, exc)
        return False, code
    except Exception as exc:  # noqa: BLE001
        log.warning("send to %s failed: %s", chat_id, exc)
        return False, None


def _chunks(text, limit=3800):
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) + 2 > limit:
            out.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


def send_long(chat_id, text):
    """Send a possibly long message, split across the 4096-char limit."""
    last = None
    for chunk in _chunks(text):
        ok, code = send_message(chat_id, chunk)
        last = code
        if not ok:
            return False, code
        time.sleep(0.3)
    return True, last


# --- formatting ---
def _header():
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(config.TIMEZONE))
    except Exception:  # noqa: BLE001
        now = datetime.now()
    return f"\u2600\ufe0f <b>Not\u00edcias de tech \u2014 {now:%d/%m}</b>"


def format_digest(digest, raw_items):
    if digest:
        lines = [_header(), ""]
        for i, d in enumerate(digest, 1):
            lines.append(f"{i}. <b>{html.escape(d.get('title', ''))}</b> \u2014 <i>{html.escape(d.get('source', ''))}</i>")
            if d.get("why"):
                lines.append(f"   {html.escape(d['why'])}")
            if d.get("url"):
                lines.append(f"   {html.escape(d['url'])}")
            if d.get("short_hook"):
                lines.append(f"   \U0001f3ac <i>Short:</i> {html.escape(d['short_hook'])}")
            lines.append("")
        return "\n".join(lines)

    lines = [_header(), "", "<i>(sem curadoria \u2014 agent indispon\u00edvel)</i>", ""]
    for i, c in enumerate(raw_items[: config.MAX_DIGEST], 1):
        lines.append(f"{i}. <b>{html.escape(c['title'])}</b> \u2014 <i>{html.escape(c['source'])}</i>")
        lines.append(f"   {html.escape(c['url'])}")
        lines.append("")
    return "\n".join(lines)
