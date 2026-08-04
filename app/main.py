"""Always-up bot: listens for subscribe/unsubscribe commands and broadcasts
the morning digest to all subscribers at DIGEST_TIME."""
import logging
import signal
import sys
from datetime import datetime

import agent
import config
import feeds
import store
import telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("main")

_running = True


def _stop(*_):
    global _running
    _running = False
    log.info("shutdown signal received")


def _now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(config.TIMEZONE))
    except Exception:  # noqa: BLE001
        return datetime.now()


def run_digest(conn):
    candidates = feeds.collect_new(conn)
    if not candidates:
        log.info("digest: no new items")
        return
    subs = store.list_subscribers(conn)
    if not subs:
        log.info("digest: no subscribers; marking %d items seen", len(candidates))
        feeds.mark_all(conn, candidates)
        return

    digest = agent.curate(candidates)
    text = telegram.format_digest(digest, candidates)
    sent = 0
    for chat_id in subs:
        ok, code = telegram.send_long(chat_id, text)
        if not ok and code == 403:
            store.remove_subscriber(conn, chat_id)
            log.info("removed blocked subscriber %s", chat_id)
        elif ok:
            sent += 1
    feeds.mark_all(conn, candidates)
    log.info("digest sent to %d/%d subscribers (%s items)",
             sent, len(subs), len(digest) if digest else "raw")


def maybe_digest(conn):
    now = _now()
    if store.get_state(conn, "last_digest_date") == now.date().isoformat():
        return
    hh, mm = (int(x) for x in config.DIGEST_TIME.split(":"))
    if (now.hour, now.minute) >= (hh, mm):
        run_digest(conn)
        store.set_state(conn, "last_digest_date", now.date().isoformat())


def handle_update(conn, upd):
    msg = upd.get("message") or upd.get("edited_message") or {}
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    name = chat.get("first_name") or chat.get("username") or ""
    cmd = text.split()[0].lower().split("@")[0]
    is_admin = config.ADMIN_CHAT_ID and str(chat_id) == str(config.ADMIN_CHAT_ID)

    if cmd == "/start":
        store.add_subscriber(conn, chat_id, name)
        telegram.send_message(chat_id, "\u2705 Inscrito! Voc\u00ea recebe o resumo de tech toda manh\u00e3.\n/stop pra sair \u2022 /help pra ajuda.")
        log.info("subscribed %s (%s)", chat_id, name)
    elif cmd == "/stop":
        store.remove_subscriber(conn, chat_id)
        telegram.send_message(chat_id, "Voc\u00ea saiu da lista. /start pra voltar quando quiser.")
        log.info("unsubscribed %s", chat_id)
    elif cmd == "/help":
        telegram.send_message(chat_id, "Comandos:\n/start \u2014 inscrever\n/stop \u2014 sair\n/help \u2014 esta mensagem")
    elif cmd == "/list" and is_admin:
        rows = store.list_subscribers_full(conn)
        body = "\n".join(f"\u2022 {n or '?'} ({cid})" for cid, n, ts in rows) or "(nenhum inscrito)"
        telegram.send_message(chat_id, f"<b>Inscritos ({len(rows)})</b>\n{body}")
    elif cmd == "/now" and is_admin:
        telegram.send_message(chat_id, "Disparando digest agora\u2026")
        run_digest(conn)


def main():
    if not config.BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN required")
        sys.exit(1)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    conn = store.open_db()
    feeds.seed_if_empty(conn)
    offset = store.get_state(conn, "offset")
    offset = int(offset) if offset else None
    log.info("bot up; polling. digest at %s (%s)", config.DIGEST_TIME, config.TIMEZONE)

    while _running:
        updates = telegram.get_updates(offset, config.POLL_TIMEOUT)
        for upd in updates:
            try:
                handle_update(conn, upd)
            except Exception as exc:  # noqa: BLE001
                log.warning("update handling error: %s", exc)
            offset = upd["update_id"] + 1
        if updates:
            store.set_state(conn, "offset", offset)
        try:
            maybe_digest(conn)
        except Exception as exc:  # noqa: BLE001
            log.warning("digest error: %s", exc)

    conn.close()
    log.info("stopped cleanly")


if __name__ == "__main__":
    main()
