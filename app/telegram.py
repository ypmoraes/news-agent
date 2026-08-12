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


_cover_cache = None


def _bot_cover():
    """Fetch the bot's profile photo (cached after the first successful call).

    Returns JPEG bytes or None.
    """
    global _cover_cache
    if _cover_cache is not None:
        return _cover_cache
    try:
        me = requests.get(_url("getMe"), timeout=10).json()
        bot_id = me["result"]["id"]
        photos = requests.get(
            _url("getUserProfilePhotos"),
            params={"user_id": bot_id, "limit": 1},
            timeout=10,
        ).json()
        file_id = photos["result"]["photos"][0][-1]["file_id"]
        file_info = requests.get(_url("getFile"), params={"file_id": file_id}, timeout=10).json()
        file_path = file_info["result"]["file_path"]
        token = config.BOT_TOKEN
        img = requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=20)
        _cover_cache = img.content
        return _cover_cache
    except Exception as exc:  # noqa: BLE001
        log.warning("could not fetch bot cover: %s", exc)
        return None


def send_audio(chat_id, mp3_bytes, title, performer):
    """Send audio file with cover art. Returns (ok, status_code)."""
    cover = _bot_cover()
    try:
        files = {"audio": ("podcast.mp3", mp3_bytes, "audio/mpeg")}
        if cover:
            files["thumbnail"] = ("cover.jpg", cover, "image/jpeg")
        r = requests.post(
            _url("sendAudio"),
            data={"chat_id": chat_id, "title": title, "performer": performer},
            files=files,
            timeout=120,
        )
        if r.status_code == 403:
            return False, 403
        r.raise_for_status()
        return True, r.status_code
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        log.warning("send_audio to %s failed: %s", chat_id, exc)
        return False, code
    except Exception as exc:  # noqa: BLE001
        log.warning("send_audio to %s failed: %s", chat_id, exc)
        return False, None


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
    return f"\U0001f4f0 <b>Bom Di.IA News \u2014 {now:%d/%m}</b>"


def format_digest(digest, raw_items, has_podcast=False, quotes=None):
    if digest:
        lines = [_header(), ""]
        if has_podcast:
            lines += ["\U0001f3d9 <b>Bom Di.IA News</b> \u2014 ou\u00e7a o podcast desta edi\u00e7\u00e3o logo abaixo", ""]
        if quotes:
            lines += [quotes, ""]
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
