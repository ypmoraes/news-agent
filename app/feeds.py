"""RSS collection with dedup delegated to the store."""
import logging
import re
import time

import feedparser

import config
import store

log = logging.getLogger("feeds")


def _entry_id(e):
    return getattr(e, "id", None) or e.get("link") or e.get("title", "")


def _entry_time(e):
    t = e.get("published_parsed") or e.get("updated_parsed")
    return time.mktime(t) if t else 0.0


def _clean(text):
    return re.sub("<[^>]+>", "", text or "").strip()


def _passes(title):
    t = title.lower()
    if config.INCLUDE and not any(k in t for k in config.INCLUDE):
        return False
    if config.EXCLUDE and any(k in t for k in config.EXCLUDE):
        return False
    return True


def collect_new(conn):
    """Up to MAX_CANDIDATES new items (newest first) not yet seen."""
    items = []
    for source, url in config.FEEDS.items():
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("fetch failed %s: %s", source, exc)
            continue
        for e in parsed.entries:
            iid = _entry_id(e)
            if not iid or store.seen(conn, iid):
                continue
            title = e.get("title", "(sem título)")
            if not _passes(title):
                store.mark_seen(conn, iid)
                continue
            items.append({
                "id": iid,
                "source": source,
                "title": title,
                "url": e.get("link", ""),
                "summary": _clean(e.get("summary", ""))[:500],
                "ts": _entry_time(e),
            })
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[: config.MAX_CANDIDATES]


def mark_all(conn, items):
    for c in items:
        store.mark_seen(conn, c["id"])
    conn.commit()


def seed_if_empty(conn):
    """On a fresh DB, mark everything currently in the feeds as seen so the
    first real digest only contains genuinely new items."""
    if store.seen_empty(conn):
        items = collect_new(conn)
        mark_all(conn, items)
        log.info("seeded %d items on first start", len(items))
        return True
    return False
